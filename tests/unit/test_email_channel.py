"""The email channel, end to end: a signed envelope in, a reply out through the install's relay.

Four halves. The wire, over envelopes built here the way the receiving script builds them, each
refusal beside the message it accepts. The relay, which is the only way a reply leaves: a request
for `RELAY_URL` goes to the relay set up on Notifications, with its password borrowed for the one
send, and to nothing else. The routes, posting to the events address of an application whose relay
is `tests.fixtures.fake_relay` speaking SMTP on the loopback, so a reply is something a relay read
rather than something a transport said. And the receiving script itself, run under Node when this
machine has it, so the signature it makes is the one the wire checks rather than one this file
computed the same way.

Task ids: M10.5.6, M10.6.1
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from email.message import EmailMessage
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.channels import adapter
from brain.channels.adapter import (
    SECRET_ASK,
    Arrived,
    ChannelRegistryError,
    VendorAnswer,
    VendorRequest,
    channel_guides,
)
from brain.channels.email import (
    GUIDE,
    LARGEST_MESSAGE_BYTES,
    WIRE,
    WORKER_SCRIPT,
    question_of,
)
from brain.channels.inbound import MAX_BODY_BYTES
from brain.channels.relay import RELAY_URL, RelayingTransport, answer_of, message_of
from brain.channels.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, WebhookRefusedError, sign
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised
from brain.guide_views import step_view
from brain.identity.bearer import TokenAuthority
from brain.ops.channel_store import channel_secret_ref
from brain.ops.connect_steps import MAX_COPY_CHARS, GuideStep, Sketch
from brain.ops.mail import (
    RELAY_CREDENTIAL_FIELD,
    RELAY_CREDENTIAL_SLOT,
    MailAnswer,
    MailPassword,
    MailSettings,
    Message,
    Security,
    SmtpTransport,
)
from brain.tables.channel import RefusedBecause
from tests.fixtures.fake_relay import Relay, fake_relay
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier
from tests.unit.test_channel_pipeline import (
    Directory,
    KeptVault,
    Store,
    Transport,
    World,
    fresh_record,
    headers,
)
from tests.unit.test_mail import PASSWORD, configured

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason: nothing below is about the present.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
SECRET = "email-channel-secret-0123456789abcdef"
WRONG = "email-channel-secret-somebody-else-00"
#: The address people write to, which a reply names as its Reply-To.
WRITTEN_TO = "ask@ask.example.test"
SENDER = "person@example.test"
MESSAGE_ID = "<m-1@example.test>"
QUESTION = "What is left on the retainer?"
EVENTS = f"{API_PREFIX}/channels/email/events"


def mail(
    *,
    sender: str = f"Person <{SENDER}>",
    body: str = QUESTION + "\n",
    message_id: str = MESSAGE_ID,
    extra: Mapping[str, str] | None = None,
    html_only: bool = False,
    alternative: bool = False,
) -> str:
    """One message as a mail client writes it."""
    built = EmailMessage()
    built["From"] = sender
    built["To"] = WRITTEN_TO
    built["Subject"] = "Retainer"
    built["Message-ID"] = message_id
    for name, value in (extra or {}).items():
        built[name] = value
    if html_only:
        built.set_content(f"<p>{QUESTION}</p>", subtype="html")
    else:
        built.set_content(body)
        if alternative:
            built.add_alternative(f"<p>{QUESTION}</p>", subtype="html")
    return built.as_string()


def envelope(raw: str, verdict: str = "pass") -> bytes:
    return json.dumps({"authentication": verdict, "message": raw}).encode("utf-8")


def arrived(body: bytes, *, secret: str = SECRET, at: datetime = NOW) -> Arrived:
    stamp = str(int(at.timestamp()))
    return Arrived(
        headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(secret, stamp, body)}, body=body
    )


def read(body: bytes) -> Any:
    return WIRE.read(WIRE.verify(arrived(body), SECRET, NOW))


def reply(to: str = f"{SENDER} {MESSAGE_ID}", **tenant: str) -> VendorRequest:
    return WIRE.request_for(
        to=to,
        text="Twelve hours are left.",
        secret=SECRET,
        tenant=tenant or {"address": WRITTEN_TO},
        now=NOW,
    )


# ======================================================================== the wire, inbound


def test_a_signed_message_whose_sender_passed_is_read_as_their_question() -> None:
    """**The positive half of every refusal below.** The sender is the From address, the words
    are the plain text, the time is the signed time and a reply goes back to the sender, threaded
    under the message.

    Delete this and a wire that refused every message would pass every test in this file."""
    received = read(envelope(mail()))

    assert received.event.channel is Channel.EMAIL
    assert received.event.channel_identity == SENDER
    assert received.event.text == QUESTION
    assert received.event.external_id == MESSAGE_ID
    assert received.event.received_at == NOW
    assert received.reply_to == f"{SENDER} {MESSAGE_ID}"
    assert received.conversation is None


def test_the_plain_text_of_a_message_written_both_ways_is_what_is_read() -> None:
    """Most clients send a plain part and an HTML one. Delete this and a reader that took the
    first part it found would answer the markup."""
    assert read(envelope(mail(alternative=True))).event.text == QUESTION


@pytest.mark.parametrize(
    "tamper", ["another secret", "altered after signing", "signed long ago", "unsigned"]
)
def test_a_message_the_receiver_did_not_send_is_refused_before_it_is_read(tamper: str) -> None:
    """**Only what the channel's secret signed is believed**, over the exact bytes and the time.

    Delete this and anybody who found the events address could post a message from anybody."""
    body = envelope(mail())
    match tamper:
        case "another secret":
            sent = arrived(body, secret=WRONG)
        case "altered after signing":
            original = arrived(body)
            sent = Arrived(headers=original.headers, body=body.replace(b"retainer", b"payroll"))
        case "signed long ago":
            sent = arrived(body, at=NOW - timedelta(hours=1))
        case _:
            sent = Arrived(headers={}, body=body)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(sent, SECRET, NOW)


@pytest.mark.parametrize("verdict", ["fail", "not_checked"])
def test_a_message_whose_verdict_is_not_a_pass_has_no_sender(verdict: str) -> None:
    """**A verdict that is not a pass is a message from nobody**, signed or not: the signature
    proves who posted it, and only the verdict says who wrote it.

    Delete this and a message the receiver never checked would be answered as its From."""
    with pytest.raises(ValueError, match=verdict):
        read(envelope(mail(), verdict))


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        json.dumps({"authentication": "pass"}).encode(),
        json.dumps({"authentication": "PASS", "message": "x"}).encode(),
        json.dumps({"authentication": "pass", "message": 3}).encode(),
    ],
)
def test_an_envelope_that_is_not_one_is_unreadable(body: bytes) -> None:
    """Delete this and a signed body missing its verdict could be read with a default verdict."""
    with pytest.raises(ValueError, match="envelope"):
        read(body)


def test_a_from_naming_two_addresses_has_no_sender() -> None:
    """A From header can list several addresses, and the receiver's verdict is about one of
    them. Delete this and the second address could be answered on the first one's pass."""
    with pytest.raises(ValueError, match="From"):
        read(envelope(mail(sender=f"A <other@elsewhere.test>, B <{SENDER}>")))


def test_automatic_mail_is_never_answered() -> None:
    """Delete this and an autoresponder and this channel could answer each other for ever."""
    with pytest.raises(ValueError, match="machine-generated"):
        read(envelope(mail(extra={"Auto-Submitted": "auto-replied"})))


def test_the_question_stops_at_the_signature_and_at_the_message_it_answers() -> None:
    """**A reply to an answer does not ask the answer back.** Quoted lines, the line a client
    writes above a quoted message, and a signature are not the question.

    Delete this and every follow-up would carry the whole thread back in as the question."""
    quoted = (
        "What about March?\n\nOn Mon, 4 Mar 2019 at 09:00, Brain <ask@ask.example.test> wrote:\n"
        "> The retainer has 12 hours left.\n"
    )
    signed_off = "What about March?\n-- \nPerson, Accounts\n"
    inline = "> The retainer has 12 hours left.\nWhat about March?\n"
    assert [question_of(one) for one in (quoted, signed_off, inline)] == ["What about March?"] * 3
    assert question_of("First line.\nSecond line.\n") == "First line.\nSecond line."
    assert read(envelope(mail(body=quoted))).event.text == "What about March?"


@pytest.mark.parametrize("which", ["only quoted", "only markup"])
def test_a_message_with_no_words_of_its_own_is_unreadable(which: str) -> None:
    """Delete this and an empty question would be answered, or markup answered as words."""
    raw = mail(body="> earlier\n") if which == "only quoted" else mail(html_only=True)
    with pytest.raises(ValueError, match=r"words|plain-text"):
        read(envelope(raw))


# ======================================================================== the wire, outbound


def test_a_reply_goes_to_the_relay_threaded_under_the_question_and_names_the_address() -> None:
    """**A reply leaves by the relay, to the sender alone, with fixed words for its subject.**

    Delete this and a reply could be built for a vendor address, carry the question's subject, or
    lose its thread."""
    request = reply()
    assert request.url == "smtp:relay" == RELAY_URL
    assert request.method == "POST"
    assert dict(request.headers) == {
        "to": SENDER,
        "subject": "Re: Your question",
        "reply-to": WRITTEN_TO,
        "auto-submitted": "auto-replied",
        "in-reply-to": MESSAGE_ID,
    }
    assert request.body == b"Twelve hours are left."


def test_a_message_to_a_bare_address_is_not_threaded() -> None:
    """A test message names an address alone. Delete this and it would claim to answer a message
    that was never sent."""
    assert dict(reply(SENDER).headers) == {
        "to": SENDER,
        "subject": "Your question",
        "reply-to": WRITTEN_TO,
        "auto-submitted": "auto-replied",
    }


@pytest.mark.parametrize(
    "to",
    [
        "",
        "nobody",
        f"{SENDER},other@example.test",
        f"{SENDER} other@example.test",
        f"{SENDER} {MESSAGE_ID} extra",
        f"{SENDER} not-a-message-id",
    ],
)
def test_a_recipient_that_is_not_one_address_is_refused(to: str) -> None:
    """**This is the one place a recipient is decided.** Delete this and a second address could
    ride in behind the first."""
    with pytest.raises(ValueError, match=r"address|Message-ID"):
        reply(to)


@pytest.mark.parametrize("tenant", [{"address": ""}, {"address": "ask"}, {"other": WRITTEN_TO}])
def test_a_record_that_names_no_address_cannot_send(tenant: dict[str, str]) -> None:
    """Delete this and a reply would go out with nowhere for the answer to it to come back to."""
    with pytest.raises(ValueError, match="address"):
        reply(**tenant)


def test_the_relay_reads_every_header_the_wire_writes() -> None:
    """**The wire and the relay agree on the message.** Built by one, read by the other.

    Delete this and a header the wire wrote could be one the relay refuses, so no reply would
    ever leave, with every wire test green."""
    assert message_of(reply()) == Message(
        to=SENDER,
        subject="Re: Your question",
        body="Twelve hours are left.",
        reply_to=WRITTEN_TO,
        in_reply_to=MESSAGE_ID,
        auto_submitted="auto-replied",
    )


@pytest.mark.parametrize(
    ("answer", "judged"),
    [
        (VendorAnswer(status=250), CallOutcome.OK),
        (VendorAnswer(status=400), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=451), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=499), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=500), CallOutcome.REJECTED),
        (VendorAnswer(status=550), CallOutcome.REJECTED),
        (VendorAnswer(status=200), CallOutcome.REJECTED),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(connection_failed=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
        (VendorAnswer(), CallOutcome.REJECTED),
    ],
)
def test_the_wire_judges_the_relay_s_answer(answer: VendorAnswer, judged: CallOutcome) -> None:
    """SMTP's own codes: 250 took it, a 4xx may take it later, a 5xx refused it, and a relay
    nobody set up sent nothing. Delete this and a relay's temporary refusal could be recorded as
    final, or a relay never asked as a message that may have arrived."""
    assert WIRE.judge(answer) is judged


# ======================================================================== the relay


@dataclass
class Mailed:
    """`MailTransport` keeping each message, answering one fixed answer."""

    answer: MailAnswer = field(default_factory=lambda: MailAnswer(CallOutcome.OK))
    sent: list[Message] = field(default_factory=list)

    def send(self, message: Message) -> MailAnswer:
        self.sent.append(message)
        return self.answer


def test_a_request_for_the_relay_leaves_by_the_relay_and_any_other_by_https() -> None:
    """**One address goes to the relay, and every other to the HTTPS transport.**

    Delete this and a reply could be posted as HTTP, or a vendor's request sent as mail."""
    https, mailed = Transport(), Mailed()
    both = RelayingTransport(https, lambda: mailed)
    vendor = VendorRequest(url="https://vendor.example.test/send", headers={}, body=b"{}")

    assert both.send(reply()) == VendorAnswer(status=250)
    assert both.send(vendor) == VendorAnswer(status=200)
    assert [one.to for one in mailed.sent] == [SENDER]
    assert https.sent == [vendor]


def test_with_no_relay_set_up_nothing_leaves_and_the_reply_is_refused() -> None:
    """Delete this and a reply with no relay behind it would be recorded as a message that may
    have arrived."""
    https = Transport()
    answer = RelayingTransport(https, lambda: None).send(reply())
    assert answer == VendorAnswer()
    assert WIRE.judge(answer) is CallOutcome.REJECTED
    assert https.sent == []


def test_the_relay_has_nothing_to_read() -> None:
    """Delete this and a read addressed to the relay would be sent to the HTTPS transport."""
    both = RelayingTransport(Transport(), lambda: Mailed())
    with pytest.raises(ValueError, match="nothing to read"):
        both.read(VendorRequest(url=RELAY_URL, headers={}, body=b"", method="GET"))


@pytest.mark.parametrize(
    "headers",
    [
        {"to": SENDER, "subject": "s", "cc": "other@example.test"},
        {"to": SENDER, "subject": "s", "bcc": "other@example.test"},
        {"to": SENDER},
        {"subject": "s"},
    ],
)
def test_a_header_the_relay_does_not_carry_is_refused_rather_than_dropped(
    headers: dict[str, str],
) -> None:
    """**There is no copy to anybody else.** Delete this and a wire asking for a copy would be
    sent without it and look as though it had, or a message with no recipient would be tried."""
    with pytest.raises(ValueError, match="relay"):
        message_of(VendorRequest(url=RELAY_URL, headers=headers, body=b"x"))


@pytest.mark.parametrize(
    ("mailed", "answered"),
    [
        (MailAnswer(CallOutcome.OK), VendorAnswer(status=250)),
        (MailAnswer(CallOutcome.REJECTED, 553), VendorAnswer(status=553)),
        (MailAnswer(CallOutcome.REJECTED, 451), VendorAnswer(status=451)),
        (MailAnswer(CallOutcome.REJECTED), VendorAnswer(status=550)),
        (MailAnswer(CallOutcome.UNAVAILABLE), VendorAnswer(connection_failed=True)),
    ],
)
def test_the_relay_s_answer_is_its_code_or_that_it_could_not_be_reached(
    mailed: MailAnswer, answered: VendorAnswer
) -> None:
    """Delete this and a refusal could lose its code, so a temporary one reads as final."""
    assert answer_of(mailed) == answered


def test_a_reply_carries_its_reply_to_its_thread_and_its_mark_to_a_relay(tmp_path: Path) -> None:
    """**What the relay read**, from `tests.fixtures.fake_relay`: the three headers a reply adds,
    and none of them on a message that asks for none.

    Delete this and the headers could be named on the message and never written to the wire."""
    with fake_relay(tmp_path, username="relay_user", password=PASSWORD) as relay:
        transport = SmtpTransport(configured(relay), PASSWORD, context=relay.trusted)
        transport.send(message_of(reply()))
        transport.send(Message(to=SENDER, subject="Hello", body="A body."))

    threaded, plain = (message_from_bytes(one.data) for one in relay.delivered)
    assert (
        threaded["Reply-To"],
        threaded["In-Reply-To"],
        threaded["References"],
        threaded["Auto-Submitted"],
    ) == (WRITTEN_TO, MESSAGE_ID, MESSAGE_ID, "auto-replied")
    assert [plain[one] for one in ("Reply-To", "In-Reply-To", "References", "Auto-Submitted")] == [
        None
    ] * 4


# ======================================================================== the routes


class CountingVault(KeptVault):
    """A vault holding the relay's password, counting every read of it."""

    def __init__(self, password: str | None = PASSWORD) -> None:
        super().__init__()
        self.reads = 0
        if password is not None:
            self.slots[RELAY_CREDENTIAL_SLOT] = {RELAY_CREDENTIAL_FIELD: password}

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.reads += 1
        return super().read_static_kv(path)


@dataclass
class Place:
    world: World = field(default_factory=World)
    vault: CountingVault = field(default_factory=CountingVault)
    relay: Relay | None = None
    settings: MailSettings | None = None


@pytest.fixture
def place(tmp_path: Path) -> Iterator[Place]:
    here = Place()
    here.world.secrets.slots[channel_secret_ref(Channel.EMAIL).path] = SECRET
    here.world.records.kept[Channel.EMAIL] = fresh_record(
        Channel.EMAIL, tenant={"address": WRITTEN_TO}
    )
    with fake_relay(tmp_path, username="relay_user", password=PASSWORD) as relay:
        here.relay = relay
        here.settings = configured(relay)
        yield here


@pytest.fixture
def client(place: Place) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    relay = place.relay
    assert relay is not None
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
            store=Store(),
            cache=NoCache(),
        )
        world = place.world
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = MemoryLedger()
        app.state.mail_password = MailPassword(place.vault)
        app.state.mail_transport = lambda settings, password: SmtpTransport(
            settings, password, context=relay.trusted
        )
        if place.settings is not None:
            app.state.mail_settings = place.settings
        yield c


def post(c: TestClient, raw: bytes, *, secret: str = SECRET) -> Any:
    stamp = str(int(time.time()))
    return c.post(
        EVENTS,
        content=raw,
        headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(secret, stamp, raw)},
    )


def test_a_signed_message_is_answered_through_the_install_s_relay_with_its_password(
    client: TestClient, place: Place
) -> None:
    """**End to end, through the events address to a relay that read the reply.** The sender is
    bound to nobody, so the answer is the binding prompt; it went to the sender alone, threaded
    under the question, signed in with the password the vault held, and nothing went over HTTPS.

    Delete this and every other test here is a test of a piece nobody showed a relay."""
    answered = post(client, envelope(mail()))

    assert answered.status_code == 200, answered.text
    assert answered.json() == {"status": "accepted", "reply": "sent"}
    assert place.relay is not None
    (one,) = place.relay.delivered
    assert (one.rcpt_to, one.authenticated_as) == ([SENDER], "relay_user")
    parsed = message_from_bytes(one.data, policy=policy.default)
    assert (parsed["To"], parsed["Subject"], parsed["In-Reply-To"], parsed["Reply-To"]) == (
        SENDER,
        "Re: Your question",
        MESSAGE_ID,
        WRITTEN_TO,
    )
    prompt = Unrecognised(channel=Channel.EMAIL).prompt
    assert parsed.get_content().rstrip("\r\n") == prompt
    assert place.vault.reads == 1
    assert place.world.transport.sent == []
    assert place.world.deliveries.seen() == [
        ("inbound", "accepted", None),
        ("outbound", "sent", None),
    ]


def test_a_forged_message_is_refused_and_the_relay_is_never_asked(
    client: TestClient, place: Place
) -> None:
    """Delete this and a message signed with anything could reach the relay and its password."""
    answered = post(client, envelope(mail()), secret=WRONG)

    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert place.relay is not None and place.relay.delivered == []
    assert place.vault.reads == 0


def test_a_message_that_did_not_pass_is_refused_as_unreadable_and_nothing_is_sent(
    client: TestClient, place: Place
) -> None:
    """Delete this and a message the receiver judged forged could be answered through the
    route, where the wire's refusal has to become a refusal and not an answer."""
    answered = post(client, envelope(mail(), "fail"))

    assert answered.status_code == 400
    assert place.relay is not None and place.relay.delivered == []
    assert place.world.deliveries.seen() == [("inbound", "refused", "unreadable")]


@pytest.mark.parametrize("missing", ["relay", "password"])
def test_with_no_relay_or_no_password_a_reply_is_refused_and_nothing_leaves(
    place: Place, missing: str
) -> None:
    """**No relay set up, or a relay naming a user the vault holds no password for, sends
    nothing**, and says refused rather than unknown.

    Delete this and a reply with nothing behind it could try a relay with no password, or be
    recorded as a message that may have arrived."""
    if missing == "relay":
        place.settings = None
    else:
        place.vault = CountingVault(password=None)
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        world = place.world
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = MemoryLedger()
        app.state.mail_password = MailPassword(place.vault)
        if place.settings is not None:
            app.state.mail_settings = place.settings
        answered = post(c, envelope(mail()))

    assert answered.json() == {"status": "accepted", "reply": "refused"}
    assert place.relay is not None and place.relay.delivered == []
    assert world.deliveries.seen()[-1] == ("outbound", "refused", "vendor_refused")
    assert place.vault.reads == (0 if missing == "relay" else 1)
    # Nothing even connected: a relay with no password is not tried with an empty one.
    assert place.relay.lines == []


def test_a_test_message_goes_to_one_address_by_the_relay_and_answers_nothing(
    client: TestClient, place: Place
) -> None:
    """Delete this and the channel's test button could send through something other than the
    relay a reply takes, and prove nothing about it."""
    answered = client.post(
        f"{API_PREFIX}/channels/email/test", json={"to": SENDER}, headers=headers("u_admin")
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["outcome"] == "sent"
    assert place.relay is not None
    (one,) = place.relay.delivered
    parsed = message_from_bytes(one.data)
    assert (parsed["To"], parsed["Subject"], parsed["In-Reply-To"]) == (
        SENDER,
        "Your question",
        None,
    )


def test_the_list_shows_email_s_steps_and_the_address_its_worker_posts_to(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The channel's own screen carries its steps and the address to paste.** The address is
    this install's public origin and the events path, and is empty while the install names no
    public address, rather than a relative path a vendor could not reach. A channel with no
    steps yet shows none.

    Delete this and the Connect screen could draw steps the route never sends, or tell a person
    to paste an address that is not this install's."""

    def listed() -> Mapping[str, Any]:
        found = client.get(f"{API_PREFIX}/channels", headers=headers("u_admin")).json()
        return {one["channel"]: one for one in found["channels"]}

    before = listed()
    assert before["email"]["events_address"] == ""
    assert [one["key"] for one in before["email"]["steps"]] == [one.key for one in GUIDE]
    assert before["email"]["steps"][-1]["asks"] == ["address", "secret"]
    (worker,) = [one for one in before["email"]["steps"] if one["copy_text"]]
    assert (worker["copy_text"], worker["asks"]) == (WORKER_SCRIPT, ["events_address"])
    assert before["webhook"]["steps"] == []
    assert (before["whatsapp"]["events_path"], before["whatsapp"]["events_address"]) == ("", "")

    monkeypatch.setattr(
        channel_routes, "value_of", lambda name: "https://brain.example.test/auth/callback"
    )
    after = listed()
    assert after["email"]["events_address"] == (
        "https://brain.example.test/api/v1/channels/email/events"
    )
    assert after["email"]["events_path"] == "/api/v1/channels/email/events"


def test_the_relay_is_asked_on_the_send_s_thread_and_never_on_the_event_loop() -> None:
    """**Its settings are read on the loop while the send's thread waits**, so asked on the loop
    it would wait on itself for ever; it refuses instead. Asked from a thread, it builds the
    relay with the saved settings and the password borrowed for the send.

    Delete this and a caller that asked the relay on the loop would hang the process."""
    settings = MailSettings(
        host="smtp.example.test",
        port=587,
        security=Security.STARTTLS,
        sender="brain@example.test",
        username="relay_user",
    )
    built: list[tuple[MailSettings, str | None]] = []

    def build(settings: MailSettings, password: str | None) -> Mailed:
        built.append((settings, password))
        return Mailed()

    state = SimpleNamespace(
        mail_settings=settings, mail_password=MailPassword(CountingVault()), mail_transport=build
    )
    request: Any = SimpleNamespace(app=SimpleNamespace(state=state))

    async def main() -> object:
        relay = channel_routes.relay_of(request)
        with pytest.raises(RuntimeError, match="thread"):
            relay()
        return await asyncio.to_thread(relay)

    assert isinstance(asyncio.run(main()), Mailed)
    assert built == [(settings, PASSWORD)]


# ======================================================================== the steps


def test_email_s_cloudflare_steps_end_with_the_form_that_saves_its_address_and_secret() -> None:
    """Delete this and the Cloudflare path's last step could ask for a field the record does not
    take, or leave out the secret, so it would end in a form that saves nothing usable. The
    mailbox path's form is `tests/unit/test_email_mailbox.py`'s."""
    steps = channel_guides()[Channel.EMAIL]
    assert steps == GUIDE
    assert (steps[-1].path, steps[-1].asks) == ("cloudflare", ("address", SECRET_ASK))
    assert set(steps[-1].asks[:-1]) <= set(WIRE.tenant_fields)


def _module(name: str, **attributes: object) -> ModuleType:
    made = ModuleType(name)
    for key, value in attributes.items():
        setattr(made, key, value)
    return made


@pytest.mark.parametrize("which", ["no wire", "another form"])
def test_a_guide_beside_no_wire_or_ending_in_another_form_is_refused(
    monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    """Delete this and a channel's steps could be drawn with nothing their form could save."""
    real = list(adapter._channel_modules())
    ending = (
        *GUIDE[:-1],
        GuideStep(key="save", title="Save", text="Save it.", sketch=GUIDE[-1].sketch, asks=("x",)),
    )
    stray = (
        _module("brain.channels.stray", GUIDE=GUIDE)
        if which == "no wire"
        else _module("brain.channels.stray", GUIDE=ending, WIRE=WIRE)
    )
    monkeypatch.setattr(adapter, "_channel_modules", lambda: iter([*real, stray]))
    with pytest.raises(ChannelRegistryError, match=r"wire|form"):
        channel_guides()


def test_a_step_offering_text_to_copy_says_what_its_button_copies() -> None:
    """**A copy button names what it copies, and copies a script and never a document.** The
    positive half is the email steps themselves, one of which offers the receiving script.

    Delete this and a step could offer an unlabelled button, or a text too long to paste."""
    sketch = Sketch(place="Somewhere", heading="Somewhere")
    with pytest.raises(ValueError, match="copy button"):
        GuideStep(key="a", title="A", text="Do it.", sketch=sketch, copy_text="x")
    with pytest.raises(ValueError, match="copy button"):
        GuideStep(key="a", title="A", text="Do it.", sketch=sketch, copy_label="Copy")
    with pytest.raises(ValueError, match="characters to copy"):
        GuideStep(
            key="a",
            title="A",
            text="Do it.",
            sketch=sketch,
            copy_text="x" * (MAX_COPY_CHARS + 1),
            copy_label="Copy",
        )
    longest = GuideStep(
        key="a",
        title="A",
        text="Do it.",
        sketch=sketch,
        copy_text="x" * MAX_COPY_CHARS,
        copy_label="Copy",
    )
    shown = step_view(longest)
    assert (len(shown.copy_text), shown.copy_label) == (MAX_COPY_CHARS, "Copy")


# ======================================================================== the receiving script


def _node() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("no node on this machine to run the receiving script under; CI has one")
    return found


HARNESS = """
import { readFileSync } from "node:fs";
import worker from "./worker.mjs";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const seen = [];
globalThis.fetch = async (url, init) => {
  seen.push({ url, method: init.method, headers: init.headers, body: init.body });
  return { ok: input.ok };
};
let rejected = null;
const bytes = new TextEncoder().encode(input.raw);
const message = {
  from: "bounce@elsewhere.example.test",
  to: "ask@ask.example.test",
  headers: new Headers({ from: input.from }),
  raw: new Response(bytes).body,
  rawSize: input.rawSize ?? bytes.length,
  setReject(reason) { rejected = reason; },
};
await worker.email(message, input.env);
process.stdout.write(JSON.stringify({ seen, rejected }));
"""

ENV: Mapping[str, str] = {
    "BRAIN_EVENTS_URL": "https://brain.example.test/api/v1/channels/email/events",
    "BRAIN_SECRET": SECRET,
    "BRAIN_DOMAINS": "Example.test, other.example.test",
}


def run_script(
    tmp_path: Path, *, sender: str, raw: str | None = None, ok: bool = True, size: int | None = None
) -> dict[str, Any]:
    """The receiving script, run under Node on one message, with `fetch` kept rather than made."""
    (tmp_path / "worker.mjs").write_text(WORKER_SCRIPT, encoding="utf-8", newline="\n")
    (tmp_path / "harness.mjs").write_text(HARNESS, encoding="utf-8", newline="\n")
    given = {"from": sender, "raw": raw or mail(sender=sender), "ok": ok, "env": dict(ENV)}
    if size is not None:
        given["rawSize"] = size
    (tmp_path / "input.json").write_text(json.dumps(given), encoding="utf-8")
    ran = subprocess.run(
        [_node(), "harness.mjs", "input.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    assert ran.returncode == 0, ran.stderr
    found: dict[str, Any] = json.loads(ran.stdout)
    return found


def test_the_receiving_script_signs_what_the_wire_verifies(tmp_path: Path) -> None:
    """**The script and the wire are one construction, shown by running both.** What the script
    posted verifies with the channel's secret and reads as the sender's question.

    Delete this and the script offered for pasting could sign something the wire never accepts,
    which only an owner's real mail would ever show."""
    ran = run_script(tmp_path, sender=f"Person <{SENDER}>")

    assert ran["rejected"] is None
    (posted,) = ran["seen"]
    assert (posted["url"], posted["method"]) == (ENV["BRAIN_EVENTS_URL"], "POST")
    sent = {key.lower(): value for key, value in posted["headers"].items()}
    at = datetime.fromtimestamp(int(sent[TIMESTAMP_HEADER]), tz=UTC)
    received = WIRE.read(
        WIRE.verify(Arrived(headers=sent, body=posted["body"].encode("utf-8")), SECRET, at)
    )
    assert (received.event.channel_identity, received.event.text) == (SENDER, QUESTION)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(Arrived(headers=sent, body=posted["body"].encode("utf-8")), WRONG, at)


@pytest.mark.parametrize(
    "sender",
    [
        "Stranger <stranger@elsewhere.test>",
        f'"{SENDER}" <stranger@elsewhere.test>',
        f"A <stranger@elsewhere.test>, B <{SENDER}>",
        "stranger@elsewhere.test, person@example.test",
        "person@example.test.elsewhere.test",
    ],
)
def test_the_receiving_script_turns_away_mail_from_outside_the_company_unread(
    tmp_path: Path, sender: str
) -> None:
    """**Only the company's own domains are passed, judged on the address and never the name.**
    See `ONLY_A_DOMAIN_THAT_REFUSES_FORGERIES_IS_PASSED`.

    Delete this and a stranger's mail, or one with a colleague's address in its display name,
    would be posted here marked as a pass."""
    ran = run_script(tmp_path, sender=sender, raw=mail())
    assert ran["seen"] == []
    assert ran["rejected"] == "This address answers mail from colleagues only."


@pytest.mark.parametrize(
    "sender", [f'"a@elsewhere.test" <{SENDER}>', "person@OTHER.example.test", SENDER]
)
def test_the_receiving_script_passes_a_colleague_however_their_client_writes_them(
    tmp_path: Path, sender: str
) -> None:
    """The positive half of the refusals above. Delete this and a script that turned away every
    message would pass them all."""
    ran = run_script(tmp_path, sender=sender)
    assert ran["rejected"] is None
    assert len(ran["seen"]) == 1


def test_the_receiving_script_turns_away_a_message_larger_than_the_install_takes(
    tmp_path: Path,
) -> None:
    """Delete this and a message with an attachment would be refused by the install where its
    sender never hears why."""
    ran = run_script(tmp_path, sender=SENDER, size=LARGEST_MESSAGE_BYTES + 1)
    assert ran["seen"] == []
    assert ran["rejected"] == "Please send the question again without attachments."
    assert len(run_script(tmp_path, sender=SENDER, size=LARGEST_MESSAGE_BYTES)["seen"]) == 1


def test_the_receiving_script_hands_a_refusal_back_to_the_sender(tmp_path: Path) -> None:
    """Delete this and a message the install did not take would vanish without a bounce."""
    ran = run_script(tmp_path, sender=SENDER, ok=False)
    assert len(ran["seen"]) == 1
    assert ran["rejected"] == "The question could not be taken just now."


def test_the_largest_message_the_script_passes_arrives_under_the_install_s_limit() -> None:
    """**The script's limit is set against the install's, not beside it.** A message of the
    largest size the script passes, written as mail is (short lines, CRLF, quoted words), still
    arrives in an envelope the events address reads.

    Delete this and raising the script's figure could pass messages the install refuses with a
    status the sender never sees."""
    line = 'He said "twelve hours" and meant it, as the invoice says.'
    body = ""
    while len(body) < LARGEST_MESSAGE_BYTES:
        body += line + "\r\n"
    body = body[:LARGEST_MESSAGE_BYTES]
    posted = json.dumps({"authentication": "pass", "message": body}, ensure_ascii=False)
    assert LARGEST_MESSAGE_BYTES < MAX_BODY_BYTES
    assert len(posted.encode("utf-8")) < MAX_BODY_BYTES
