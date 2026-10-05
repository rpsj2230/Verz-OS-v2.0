"""The WhatsApp channel, end to end: Meta's signature in, the address checked by a GET, a batch
answered message by message, and answers out on the system user's access token.

Three parts. The wire, over Cloud API notifications built here the way Meta documents them, each
refusal beside what it accepts. The address check, which answers Meta's challenge only for the
verify token in the vault. And the events address, where a signed notification carrying two
people's messages is answered twice, to each of them, and a delivery receipt is acknowledged and
nothing else.

Task ids: M10.5.3, M10.6.1
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.channels.adapter import (
    EVENTS_ADDRESS_ASK,
    Arrived,
    BatchedWire,
    SubscribedWire,
    VendorAnswer,
    channel_guides,
    channel_wires,
)
from brain.channels.webhook import WebhookRefusedError
from brain.channels.whatsapp import (
    ACCESS_TOKEN,
    ACKNOWLEDGED,
    APP_SECRET,
    GRAPH_API_URL,
    GRAPH_API_VERSION,
    MAX_TEXT_CHARS,
    META_APPS_URL,
    PHONE_NUMBER_ID,
    SIGNATURE_HEADER,
    VERIFY_TOKEN,
    WIRE,
)
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised
from brain.identity.bearer import TokenAuthority
from brain.ops.channel_store import channel_secret_ref
from brain.ops.credentials import Credentials
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier
from tests.unit.test_channel_pipeline import (
    Directory,
    Store,
    Transport,
    World,
    fresh_record,
)

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason: nothing below is about the present.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
APP = "whatsapp-app-secret-sentinel-0123456789"
ACCESS = "EAAwhatsapp-access-token-sentinel-0123"
VERIFY = "a-word-the-person-chose-0123"
KEPT = json.dumps({APP_SECRET: APP, ACCESS_TOKEN: ACCESS, VERIFY_TOKEN: VERIFY})
NUMBER = "10987654321"
ADA, BEN = "6590000001", "6590000002"
EVENTS = f"{API_PREFIX}/channels/whatsapp/events"


def text(sender: str, words: str, wamid: str) -> dict[str, Any]:
    return {
        "from": sender,
        "id": wamid,
        "timestamp": str(int(NOW.timestamp())),
        "type": "text",
        "text": {"body": words},
    }


def notification(*messages: dict[str, Any], number: str = NUMBER, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550100", "phone_number_id": number},
        **extra,
    }
    if messages:
        value["messages"] = list(messages)
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}],
    }


def sign(body: bytes, secret: str = APP) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def arrived(body: dict[str, Any], *, secret: str = APP, signature: str | None = None) -> Arrived:
    raw = json.dumps(body).encode("utf-8")
    presented = sign(raw, secret) if signature is None else signature
    return Arrived(
        headers={SIGNATURE_HEADER.lower(): presented},
        body=raw,
        tenant={PHONE_NUMBER_ID: NUMBER},
    )


ONE = notification(text(ADA, "what is left on the retainer?", "wamid.A1"))


# ======================================================================== verifying


def test_a_notification_meta_signed_is_read_as_its_sender_and_answered_in_their_chat() -> None:
    """The positive case: verified over the exact bytes, split into its one message, and read as
    the gate's event, keyed on the WhatsApp id and never on the profile name.

    Delete this and every refusal below could be satisfied by a wire that refuses everything."""
    opened = WIRE.verify(arrived(ONE), KEPT, NOW)
    (part,) = WIRE.parts(opened)
    received = WIRE.read(part)
    assert received.event.channel is Channel.WHATSAPP
    assert received.event.channel_identity == ADA
    assert received.event.external_id == "wamid.A1"
    assert received.event.text == "what is left on the retainer?"
    assert received.reply_to == ADA
    conversation = received.conversation
    assert conversation is not None
    assert (conversation.shared, conversation.sender_to) == (False, ADA)


@pytest.mark.parametrize(
    "signature",
    [
        pytest.param(None, id="another app's secret"),
        pytest.param("", id="no signature"),
        pytest.param("sha1=" + "0" * 40, id="the old header's form"),
        pytest.param("sha256=" + "A" * 64, id="upper case"),
        pytest.param("sha256=" + "0" * 64, id="a guess"),
    ],
)
def test_a_notification_meta_did_not_sign_with_this_app_s_secret_is_refused(
    signature: str | None,
) -> None:
    """Delete this and anybody who learns the events address posts a message naming any number,
    and is answered as that person, at that person's reach."""
    posted = arrived(ONE, secret="somebody-else-s-app-secret-000", signature=signature)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(posted, KEPT, NOW)


def test_a_notification_about_another_number_is_refused() -> None:
    """**The record answers one number.** A notification Meta genuinely signed, about another
    number the same app sends from, is refused; so is one that names no number at all.

    Delete this and a second number added to the app would have its messages answered here."""
    elsewhere = notification(text(ADA, "hello", "wamid.B1"), number="19999999999")
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(elsewhere), KEPT, NOW)
    nothing = {"object": "whatsapp_business_account", "entry": []}
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(nothing), KEPT, NOW)


def test_a_secret_that_is_not_the_three_parts_refuses_every_notification() -> None:
    """Delete this and a slot holding one part alone would verify against nothing."""
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(ONE), json.dumps({APP_SECRET: APP}), NOW)


# ======================================================================== batches


def test_a_notification_of_several_messages_is_split_one_per_text_message() -> None:
    """**A batch is answered message by message.** Two people's text messages beside one image
    are two parts, each holding its own sender's message alone; the image is not read.

    Delete this and the second person's question is lost behind the first's, which is exactly
    what `normalise_messages` was written to refuse."""
    image = {"from": BEN, "id": "wamid.I1", "timestamp": "1", "type": "image", "image": {}}
    batch = notification(
        text(ADA, "first question", "wamid.A2"), image, text(BEN, "second question", "wamid.B2")
    )
    parts = WIRE.parts(WIRE.verify(arrived(batch), KEPT, NOW))
    read = [WIRE.read(one) for one in parts]
    assert [(one.event.channel_identity, one.event.text) for one in read] == [
        (ADA, "first question"),
        (BEN, "second question"),
    ]
    assert WIRE.handshake(arrived(batch)) is None


def test_a_delivery_receipt_or_an_image_alone_is_acknowledged_and_never_claimed() -> None:
    """Delete this and Meta would be answered with an error for every receipt of every answer the
    install sends, and would retry each for days."""
    receipt = notification(statuses=[{"id": "wamid.X", "status": "delivered"}])
    image = notification({"from": ADA, "id": "wamid.I2", "timestamp": "1", "type": "image"})
    for body in (receipt, image):
        opened = WIRE.verify(arrived(body), KEPT, NOW)
        assert WIRE.parts(opened) == ()
        assert WIRE.handshake(opened) == ACKNOWLEDGED


# ======================================================================== the address check


def test_meta_s_address_check_is_answered_with_its_challenge_for_the_agreed_word() -> None:
    """Delete this and Verify and save in Meta's dashboard could never pass, or would pass for
    anybody who asked."""
    asked = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
    assert WIRE.subscription_answer(asked, KEPT) == "1158201444"
    for wrong in (
        {**asked, "hub.verify_token": "another-word"},
        {**asked, "hub.mode": "unsubscribe"},
        {**asked, "hub.challenge": ""},
        {key: value for key, value in asked.items() if key != "hub.verify_token"},
    ):
        assert WIRE.subscription_answer(wrong, KEPT) is None
    assert WIRE.subscription_answer(asked, "not the parts") is None


def test_whatsapp_is_the_one_channel_that_batches_and_is_checked_by_a_get() -> None:
    """Delete this and another channel's events address could start answering GETs, or a batch
    from WhatsApp could be read as its first message."""
    wires = channel_wires()
    assert {one for one, wire in wires.items() if isinstance(wire, BatchedWire)} == {
        Channel.WHATSAPP
    }
    assert {one for one, wire in wires.items() if isinstance(wire, SubscribedWire)} == {
        Channel.WHATSAPP
    }


# ======================================================================== sending


def test_a_reply_is_a_text_message_from_the_record_s_number_on_the_access_token() -> None:
    """Delete this and the answer could go to another host, from another number, or on a
    credential that is not the one kept for sending."""
    made = WIRE.request_for(
        to=ADA, text="Hello.", secret=KEPT, tenant={PHONE_NUMBER_ID: NUMBER}, now=NOW
    )
    assert made.url == f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{NUMBER}/messages"
    assert made.headers["Authorization"] == f"Bearer {ACCESS}"
    assert json.loads(made.body) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": ADA,
        "type": "text",
        "text": {"preview_url": False, "body": "Hello."},
    }
    assert ACCESS not in repr(made) and APP not in made.headers["Authorization"]


@pytest.mark.parametrize(
    ("to", "tenant", "text_length"),
    [
        ("+6590000001", {PHONE_NUMBER_ID: NUMBER}, 5),
        ("ada", {PHONE_NUMBER_ID: NUMBER}, 5),
        (ADA, {}, 5),
        (ADA, {PHONE_NUMBER_ID: "../other"}, 5),
        (ADA, {PHONE_NUMBER_ID: NUMBER}, MAX_TEXT_CHARS + 1),
    ],
)
def test_a_reply_that_is_not_one_text_to_one_id_from_one_number_is_refused(
    to: str, tenant: dict[str, str], text_length: int
) -> None:
    """Delete this and a malformed id or number would be put into the Graph API's path."""
    with pytest.raises(ValueError, match=r"."):
        WIRE.request_for(to=to, text="x" * text_length, secret=KEPT, tenant=tenant, now=NOW)


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (VendorAnswer(status=200, body=b'{"messages":[{"id":"wamid.S"}]}'), CallOutcome.OK),
        (VendorAnswer(status=200, body=b"{}"), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=400, body=b'{"error":{"code":131047}}'), CallOutcome.REJECTED),
        (VendorAnswer(status=400, body=b'{"error":{"code":130429}}'), CallOutcome.QUOTA),
        (VendorAnswer(status=429), CallOutcome.QUOTA),
        (VendorAnswer(status=500), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=302), CallOutcome.REJECTED),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
    ],
)
def test_the_wire_judges_the_cloud_api_s_answer(answer: VendorAnswer, outcome: CallOutcome) -> None:
    """Delete this and a message outside the twenty-four hours would be recorded as sent, or a
    rate limit as a refusal nobody retries."""
    assert WIRE.judge(answer) is outcome


def test_whatsapp_s_steps_end_with_the_webhook_after_the_form() -> None:
    """Delete this and the flow could ask for the webhook before the set-up that answers Meta's
    check is saved, which makes Verify and save fail every time."""
    steps = channel_guides()[Channel.WHATSAPP]
    assert [one.key for one in steps] == ["app", "token", "secret", "save", "webhook"]
    assert steps[3].asks == (PHONE_NUMBER_ID, APP_SECRET, ACCESS_TOKEN, VERIFY_TOKEN)
    assert steps[4].asks == (EVENTS_ADDRESS_ASK,)
    assert steps[0].link == META_APPS_URL


# ======================================================================== the routes


@pytest.fixture
def world() -> World:
    here = World()
    here.secrets.slots[channel_secret_ref(Channel.WHATSAPP).path] = KEPT
    here.records.kept[Channel.WHATSAPP] = fresh_record(
        Channel.WHATSAPP, tenant={PHONE_NUMBER_ID: NUMBER}
    )
    here.transport = Transport(
        answer=VendorAnswer(status=200, body=b'{"messages":[{"id":"wamid.S"}]}')
    )
    return here


@pytest.fixture
def client(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", "https://brain.example.test/callback")
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
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
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = MemoryLedger()
        app.state.credentials = Credentials(world.vault)
        yield c


def post(c: TestClient, body: dict[str, Any], *, secret: str = APP) -> Any:
    raw = json.dumps(body).encode("utf-8")
    return c.post(EVENTS, content=raw, headers={SIGNATURE_HEADER: sign(raw, secret)})


def test_two_people_in_one_notification_are_each_answered_in_their_own_chat(
    client: TestClient, world: World
) -> None:
    """**End to end, through the events address.** Both senders are bound to nobody, so each is
    sent the binding prompt, to their own id, on the access token, and both messages are
    recorded as accepted.

    Delete this and every other test here is a test of a piece nobody showed the route."""
    batch = notification(text(ADA, "first", "wamid.A3"), text(BEN, "second", "wamid.B3"))
    answered = post(client, batch)
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "accepted"
    sent = sorted(json.loads(one.body)["to"] for one in world.transport.sent)
    assert sent == [ADA, BEN]
    assert {json.loads(one.body)["text"]["body"] for one in world.transport.sent} == {
        Unrecognised(channel=Channel.WHATSAPP).prompt
    }
    inbound = [
        one
        for one in world.deliveries.entries
        if one.direction is Direction.INBOUND and one.outcome is DeliveryOutcome.ACCEPTED
    ]
    assert len(inbound) == 2


def test_a_delivery_receipt_is_acknowledged_and_nothing_is_sent_or_claimed(
    client: TestClient, world: World
) -> None:
    """Delete this and every receipt of every answer would be refused, and Meta would retry it."""
    receipt = notification(statuses=[{"id": "wamid.X", "status": "read"}])
    answered = post(client, receipt)
    assert (answered.status_code, answered.json()) == (200, dict(ACKNOWLEDGED))
    assert world.transport.sent == []
    assert world.claims.asked == 0 and world.deliveries.entries == []


def test_a_notification_whose_messages_are_not_a_list_is_refused_as_unreadable(
    client: TestClient, world: World
) -> None:
    """Delete this and a signed notification of an unexpected shape could answer Meta with a
    server error, which it retries for days, rather than with one recorded refusal."""
    malformed = notification()
    malformed["entry"][0]["changes"][0]["value"]["messages"] = {"not": "a list"}
    answered = post(client, malformed)
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.UNREADABLE][0]
    assert world.transport.sent == []
    assert [(one.outcome, one.reason) for one in world.deliveries.entries] == [
        (DeliveryOutcome.REFUSED, RefusedBecause.UNREADABLE)
    ]


def test_a_notification_signed_with_another_secret_is_refused_and_nothing_is_sent(
    client: TestClient, world: World
) -> None:
    """Delete this and a forged notification could make the number speak."""
    answered = post(client, ONE, secret="somebody-else-s-app-secret-000")
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert world.transport.sent == []


def test_the_address_check_answers_meta_s_challenge_for_the_agreed_word_alone(
    client: TestClient, world: World
) -> None:
    """**Meta's GET, through the route.** The agreed word gets the challenge back as plain text;
    another word, a switched-off record and a channel with no such check get nothing.

    Delete this and Verify and save could never pass, or a GET could learn which channels an
    install has set up."""
    asked = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "8675309"}
    answered = client.get(EVENTS, params=asked)
    assert (answered.status_code, answered.text) == (200, "8675309")
    assert answered.headers["content-type"].startswith("text/plain")

    wrong = client.get(EVENTS, params={**asked, "hub.verify_token": "another-word"})
    assert wrong.status_code == 403 and "8675309" not in wrong.text
    slack = client.get(f"{API_PREFIX}/channels/slack/events", params=asked)
    assert slack.status_code == 404

    world.records.kept[Channel.WHATSAPP] = fresh_record(
        Channel.WHATSAPP, enabled=False, tenant={PHONE_NUMBER_ID: NUMBER}
    )
    off = client.get(EVENTS, params=asked)
    assert off.status_code == 404
