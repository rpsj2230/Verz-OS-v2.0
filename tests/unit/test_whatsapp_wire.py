"""WhatsApp's wire: a request is Meta's only if the app secret signed its exact bytes.

Two claims carry this file, and each is held from both sides.

**The signature is checked over the bytes that arrived, before anything reads them.** Every
refusal below goes through `brain.channels.inbound.receive` with a wire that counts how often it
was asked to read a body, and the count is zero; the one request Meta did sign is read once. The
signature itself is recomputed here from `hmac` and `hashlib`, not from the module, so a check that
agreed with itself about the wrong construction would fail.

**Nothing is sent back, and a reply is recorded as refused, never as sent.** The Cloud API send is
not built, so the wire refuses every reply and `deliver` records it as incomplete with the
transport never asked.

Task ids: M10.6.2
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.channels.adapter import Arrived, channel_wires
from brain.channels.inbound import ReceiptKind, receive
from brain.channels.outbound import Outgoing, deliver
from brain.channels.webhook import WebhookRefusedError
from brain.channels.whatsapp import (
    A_REPLY_ON_WHATSAPP_IS_NOT_BUILT,
    SIGNATURE_HEADER,
    WIRE,
    WhatsAppWire,
    signature_for,
    verify_signature,
)
from brain.gate.context import Channel
from brain.ops.acceptance_checks_channels import whatsapp_message
from brain.ops.channel_store import channel_secret_ref
from brain.ops.idempotency import Intent
from brain.tables.channel import DeliveryOutcome, RefusedBecause
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_channel_pipeline import Claims, Deliveries, Secrets, Transport, fresh_record

#: The app secret every request here is signed with. Not one Meta issued.
APP_SECRET = "a0" * 16

#: The sender and the message, as Meta posts them.
SENDER = "999000000001"
MESSAGE = whatsapp_message(SENDER, "what is left on the retainer?")
RAW = json.dumps(MESSAGE).encode()


def meta_signs(secret: str, body: bytes) -> str:
    """What Meta sends in `X-Hub-Signature-256`, computed here and not by the module under test."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Reading(WhatsAppWire):
    """The WhatsApp wire, counting how often it looked inside a body."""

    reads: int = 0

    def read(self, arrived: Arrived) -> Any:
        object.__setattr__(self, "reads", self.reads + 1)
        return super().read(arrived)


def received(body: bytes, headers: dict[str, str], wire: Reading) -> Any:
    """One request through `receive` as the events route hands it over, on a switched-on record
    whose slot holds `APP_SECRET`."""

    async def the_bytes() -> bytes:
        return body

    return asyncio.run(
        receive(
            wire,
            record=fresh_record(Channel.WHATSAPP, tenant={}),
            headers=headers,
            declared_length=len(body),
            body=the_bytes,
            secrets=Secrets(slots={channel_secret_ref(Channel.WHATSAPP).path: APP_SECRET}),
            claims=Claims(),
            deliveries=Deliveries(),
            now=datetime.now(UTC),
        )
    )


def test_a_body_signed_with_the_app_secret_is_read_once_as_its_one_message() -> None:
    """The positive case, so the refusals below cannot be satisfied by a wire refusing everything:
    Meta's signature over the exact bytes is accepted, the body is read once, and the message is
    the sender's own question with the sender to reply to. Delete this and a wire that refused
    every request would pass every test in this file."""
    wire = Reading()
    receipt = received(RAW, {SIGNATURE_HEADER: meta_signs(APP_SECRET, RAW)}, wire)
    assert receipt.kind is ReceiptKind.ACCEPTED and wire.reads == 1
    assert receipt.inbound is not None and receipt.reply_to == SENDER
    assert receipt.inbound.event.channel_identity == SENDER
    assert receipt.inbound.event.text == "what is left on the retainer?"
    assert signature_for(APP_SECRET, RAW) == meta_signs(APP_SECRET, RAW)


#: One altered byte: the question's first letter, so the altered bytes are still a message.
ALTERED = RAW.replace(b'"what is left', b'"What is left', 1)
#: The same JSON written out again without spaces, which is what verifying a parsed body signs.
REWRITTEN = json.dumps(MESSAGE, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        pytest.param(RAW, {}, id="no signature"),
        pytest.param(RAW, {SIGNATURE_HEADER: meta_signs("b1" * 16, RAW)}, id="another secret"),
        pytest.param(ALTERED, {SIGNATURE_HEADER: meta_signs(APP_SECRET, RAW)}, id="one byte"),
        pytest.param(RAW, {SIGNATURE_HEADER: meta_signs(APP_SECRET, REWRITTEN)}, id="rewritten"),
        pytest.param(
            RAW, {SIGNATURE_HEADER: meta_signs(APP_SECRET, RAW).upper()}, id="another spelling"
        ),
        pytest.param(
            RAW,
            {SIGNATURE_HEADER: meta_signs(APP_SECRET, RAW).removeprefix("sha256=")},
            id="no algorithm",
        ),
    ],
)
def test_an_unsigned_forged_altered_or_rewritten_request_is_refused_before_it_is_read(
    body: bytes, headers: dict[str, str]
) -> None:
    """`A_WHATSAPP_REQUEST_IS_SIGNED_BY_META_OR_REFUSED`. Each is refused as a bad signature and
    the wire never looks inside the body. Delete this and a request nobody signed, or one changed
    in flight, is parsed and answered as a person's message."""
    assert ALTERED != RAW and len(ALTERED) == len(RAW)
    wire = Reading()
    receipt = received(body, headers, wire)
    assert receipt.kind is ReceiptKind.REFUSED
    assert receipt.reason is RefusedBecause.BAD_SIGNATURE and wire.reads == 0


def test_an_empty_app_secret_verifies_nothing() -> None:
    """`AN_EMPTY_KEY_VERIFIES_NOTHING`: an HMAC under an empty key is one anybody can compute, and
    here it is computed correctly and still refused. Delete this and a slot holding an empty value
    accepts every forged request as signed."""
    with pytest.raises(WebhookRefusedError):
        verify_signature(app_secret="", signature=meta_signs("", RAW), body=RAW)
    verify_signature(app_secret=APP_SECRET, signature=meta_signs(APP_SECRET, RAW), body=RAW)


def test_a_signature_outside_ascii_is_refused_and_does_not_raise_anything_else() -> None:
    """`hmac.compare_digest` raises `TypeError` for a string outside ASCII, and a header is whatever
    was sent. Compared as bytes, it is one more signature that does not match. Delete this and a
    stranger's header turns a refusal into an error the route never meant to answer."""
    with pytest.raises(WebhookRefusedError):
        verify_signature(app_secret=APP_SECRET, signature="sha256=éé", body=RAW)


def test_a_parsed_body_is_refused_as_something_meta_never_signed() -> None:
    """The check takes the bytes and nothing else, for `brain.channels.webhook.assert_raw_bytes`'s
    reason. Delete this and a caller can verify a re-serialisation of what arrived."""
    with pytest.raises(TypeError):
        verify_signature(
            app_secret=APP_SECRET,
            signature=meta_signs(APP_SECRET, RAW),
            body=MESSAGE,  # type: ignore[arg-type]
        )


def test_a_verified_body_that_is_not_one_text_message_is_unreadable_and_not_guessed() -> None:
    """The events address claims one message per request, so a delivery of several, or of none
    that is text, is refused as unreadable rather than read as its first. Delete this and one
    sender's question is answered while another's in the same delivery is dropped unsaid."""
    two = json.loads(RAW)
    messages = two["entry"][0]["changes"][0]["value"]["messages"]
    messages.append({**messages[0], "id": "wamid.second"})
    image = json.loads(RAW)
    image["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
    for body in (json.dumps(two).encode(), json.dumps(image).encode(), b"[]", b"not json"):
        with pytest.raises(ValueError):
            WIRE.read(Arrived(headers={}, body=body))


def test_a_reply_on_whatsapp_is_recorded_refused_and_never_reaches_the_vendor() -> None:
    """`A_REPLY_ON_WHATSAPP_IS_NOT_BUILT`, through the one send: the wire builds no request, so
    `deliver` records the reply as refused and incomplete and the transport is never asked. Delete
    this and a WhatsApp channel set up on an install could be recorded as sending what it cannot."""
    with pytest.raises(ValueError, match="sends nothing back"):
        WIRE.request_for(
            to=SENDER, text="Hello.", secret=APP_SECRET, tenant={}, now=datetime.now(UTC)
        )
    transport, deliveries = Transport(), Deliveries()
    ledger = MemoryLedger()
    delivered = asyncio.run(
        deliver(
            Outgoing(
                channel=Channel.WHATSAPP,
                to=SENDER,
                intent=Intent(principal_id="u_admin", intent_ref="whatsapp.reply.1"),
                text="Hello.",
            ),
            record=fresh_record(Channel.WHATSAPP, tenant={}),
            secrets=Secrets(slots={channel_secret_ref(Channel.WHATSAPP).path: APP_SECRET}),
            reach=_NoReach(),
            transport=transport,
            ledger=lambda work: work(ledger),
            deliveries=deliveries,
            now=datetime.now(UTC),
        )
    )
    assert (delivered.outcome, delivered.reason) == (
        DeliveryOutcome.REFUSED,
        RefusedBecause.INCOMPLETE,
    )
    assert transport.sent == [] and deliveries.seen() == [("outbound", "refused", "incomplete")]
    assert "sends nothing back" in A_REPLY_ON_WHATSAPP_IS_NOT_BUILT


class _NoReach:
    """A reply to nobody in particular asks no reach; asked, this says so loudly."""

    async def load(self, principal_id: str, now: datetime) -> Any:
        raise AssertionError("a product sentence was held to somebody's reach")


def test_the_registry_finds_the_whatsapp_wire_beside_its_adapter() -> None:
    """The events address receives exactly the channels with a wire, so this is what makes
    WhatsApp received at all. Delete this and the wire can drop out of discovery with every test
    of it still green and every WhatsApp request answered as an address with nothing at it."""
    assert channel_wires()[Channel.WHATSAPP] is WIRE
    assert WIRE.channel is Channel.WHATSAPP and WIRE.tenant_fields == ()
    assert WIRE.handshake(Arrived(headers={}, body=RAW)) is None
