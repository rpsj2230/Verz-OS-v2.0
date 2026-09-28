"""What every channel does with a request before anything answers it: switched on, verified, read,
claimed, then addressed.

Every adapter turns what arrived into a `brain.gate.ingress.ChannelEvent` through
`ChannelAdapter.normalise`, and nothing after that step asked whether the message had been seen
before. A provider that redelivers on a timeout, which is every webhook provider, would then be
answered twice, and a message asking for a side effect would have it done twice. This is the one
step between an adapter and the answer, so no adapter can reach the gate without it.

**`receive` is the whole receiving half, in an order that is the rule (M10.2.1, M10.6.3).** The
channel's record first: no record, or a record switched off, is refused before a byte of the body
is read. Then the size the request declares, and then the bytes, refused above `MAX_BODY_BYTES`.
Then the channel's secret, borrowed for this one check. Then the signature over the exact bytes,
by the channel's wire, and **a request that does not verify is refused before the wire reads it**:
`ChannelWire.read` is the first thing that looks inside the body, and it is reached only by a
request that verified. Then the read, then the claim. See
`A_REQUEST_IS_REFUSED_BEFORE_ITS_BODY_IS_READ`.

**Every refusal is recorded, and none of its content is (M10.6.1).** One `ops.channel_delivery`
row per refusal naming the channel and the reason, one per redelivery and one per accepted
message, through `brain.ops.channel_store.DeliveryEntry`, which has no field that could hold a
body, a sender or a message id. A request to a channel this release cannot receive on is answered
as absent by the route and never reaches here, because there is no channel there to record it
against.

**The claim is the database's (M3.2.2).** `brain.gate.event_store.first_delivery` inserts the
dedupe key and reports whether its row went in; a redelivery is refused by the primary key of
`gate.channel_event`, whichever of two concurrent deliveries commits first. It is committed before
the answer is made, by `brain.ops.channel_store.StoredClaims`, so a retry arriving while the first
delivery is still being answered is a redelivery, and one message is answered once.

**A sender bound to nobody is told how to bind and nothing else (M10.3.3).** `reply_for` looks the
sender up by `brain.gate.ingress.identity_hash`, never by the raw identity, and a sender with no
binding is sent `brain.gate.ingress.Unrecognised`'s prompt: the same words whether the identity was
never seen, is known and unbound, or was unbound this morning, and no entitlement at all. Until the
binding table exists (CH2's) nobody is bound, and `NoBindingsYet` says so rather than guessing.

**A chat addresses an agent with a mention that opens the message (M3.9.8).**
`brain.gate.addressing.from_mention` takes a leading `@agent_id` off the question, and only a
leading one, for the reason that module gives about quoted text choosing an agent.

Task ids: M3.2.2, M3.9.8, M10.2.1, M10.3.3, M10.6.1, M10.6.3
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from brain.channels.adapter import Arrived, ChannelAdapter, ChannelWire
from brain.channels.outbound import Outgoing
from brain.channels.webhook import WebhookRefusedError
from brain.gate.addressing import Address, from_mention
from brain.gate.context import Channel
from brain.gate.event_store import first_delivery
from brain.gate.ingress import Binding, ChannelEvent, Unrecognised, identity_hash
from brain.ops.channel_store import (
    ChannelRecord,
    ChannelSecrets,
    ChannelSecretsUnavailableError,
    DeliveryEntry,
    DeliveryRecords,
    EventClaims,
)
from brain.ops.idempotency import Intent
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause

# ------------------------------------------------------------------ written-down reasons

#: Why the order of `receive` is the rule.
A_REQUEST_IS_REFUSED_BEFORE_ITS_BODY_IS_READ: Final = (
    "A channel switched off, or never configured, is refused before a byte of the body is read, "
    "and a request whose signature does not verify is refused before the wire reads the body it "
    "sent. Reading first and refusing after would parse an attacker's bytes on the one path that "
    "exists to refuse them, and a parser is where a crafted body does its work."
)

#: Why nobody is bound before the binding table exists.
NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT: Final = (
    "No table holds a channel binding in this release, so no sender is bound to anybody and "
    "every sender is answered as unrecognised. That is the narrow direction: a sender who should "
    "have been answered is told how to bind, and nobody is answered as somebody they are not."
)

#: The largest body read. A chat message with its envelope, never a document: a vendor that
#: sends a file sends a reference to it.
MAX_BODY_BYTES: Final = 256 * 1024


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class Inbound:
    """A message claimed as its first delivery, and what it asks of whom."""

    event: ChannelEvent
    address: Address


class ReceiptKind(enum.StrEnum):
    """How far a request got."""

    REFUSED = "refused"
    #: The vendor checking the address. Answered, and never claimed.
    HANDSHAKE = "handshake"
    REDELIVERED = "redelivered"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class Receipt:
    """What `receive` came to. `inbound` and `reply_to` are set exactly when it was accepted."""

    kind: ReceiptKind
    reason: RefusedBecause | None = None
    handshake: Mapping[str, str] | None = None
    inbound: Inbound | None = None
    reply_to: str = ""


class ChannelBindings(Protocol):
    """Who a channel identity is bound to, looked up by its digest. CH2 keeps the table."""

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        """The live binding for this identity digest on this channel, or None."""
        ...


class ChannelAnswerer(Protocol):
    """What answers a bound sender: the gate, run as them. The chat channel's package wires it."""

    async def answer(
        self, inbound: Inbound, *, binding: Binding, reply_to: str, now: datetime
    ) -> Outgoing:
        """The answer to send, made at the bound person's reach and carrying its hash."""
        ...


class NoBindingsYet:
    """`ChannelBindings` before a binding is kept: `NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT`."""

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        del channel, digest
        return None


# ------------------------------------------------------------------------ the receiving half


async def _refuse(deliveries: DeliveryRecords, channel: Channel, reason: RefusedBecause) -> Receipt:
    await deliveries.record(
        DeliveryEntry(
            channel=channel,
            direction=Direction.INBOUND,
            outcome=DeliveryOutcome.REFUSED,
            reason=reason,
        )
    )
    return Receipt(kind=ReceiptKind.REFUSED, reason=reason)


async def receive(
    wire: ChannelWire,
    *,
    record: ChannelRecord | None,
    headers: Mapping[str, str],
    declared_length: int | None,
    body: Callable[[], Awaitable[bytes]],
    secrets: ChannelSecrets,
    claims: EventClaims,
    deliveries: DeliveryRecords,
    now: datetime,
) -> Receipt:
    """One request to one channel, taken as far as it may go, and recorded however far that is.

    `body` is how the bytes are read, and it is called only once the record is on and the declared
    size is within bounds. `headers` have lower-cased names. Does not answer: a claimed message is
    handed back for `reply_for` and the route. See the module docstring for the order.
    """
    channel = wire.channel
    if record is None:
        return await _refuse(deliveries, channel, RefusedBecause.NOT_CONFIGURED)
    if not record.enabled:
        return await _refuse(deliveries, channel, RefusedBecause.SWITCHED_OFF)
    if declared_length is not None and declared_length > MAX_BODY_BYTES:
        return await _refuse(deliveries, channel, RefusedBecause.TOO_LARGE)

    raw = await body()
    if len(raw) > MAX_BODY_BYTES:
        return await _refuse(deliveries, channel, RefusedBecause.TOO_LARGE)

    try:
        secret = await asyncio.to_thread(secrets.read, record.secret)
    except ChannelSecretsUnavailableError:
        return await _refuse(deliveries, channel, RefusedBecause.VAULT_UNAVAILABLE)
    if secret is None:
        return await _refuse(deliveries, channel, RefusedBecause.NO_SECRET)

    arrived = Arrived(headers=headers, body=raw)
    try:
        wire.verify(arrived, secret, now)
    except WebhookRefusedError:
        return await _refuse(deliveries, channel, RefusedBecause.BAD_SIGNATURE)
    del secret

    handshake = wire.handshake(arrived)
    if handshake is not None:
        return Receipt(kind=ReceiptKind.HANDSHAKE, handshake=handshake)

    try:
        received = wire.read(arrived)
        first = await claims.first(received.event)
    except ValueError:
        # `ExternalIdTooLongError` is one: an id the dedupe key cannot hold is refused rather
        # than truncated, for `brain.gate.event_store`'s reason.
        return await _refuse(deliveries, channel, RefusedBecause.UNREADABLE)

    outcome = DeliveryOutcome.ACCEPTED if first else DeliveryOutcome.REDELIVERED
    await deliveries.record(
        DeliveryEntry(channel=channel, direction=Direction.INBOUND, outcome=outcome)
    )
    if not first:
        return Receipt(kind=ReceiptKind.REDELIVERED)
    return Receipt(
        kind=ReceiptKind.ACCEPTED,
        inbound=Inbound(event=received.event, address=from_mention(received.event.text)),
        reply_to=received.reply_to,
    )


def reply_intent(record: ChannelRecord, event: ChannelEvent) -> Intent:
    """The intent a reply to this message is sent under: one per message, whoever asks again.

    The principal is whoever last set the channel up, because the reply is made under their
    decision to switch it on, as `brain.ops.outbox_store.delivery_operation` keys a webhook on its
    subscriber's creator. The message is named by a digest of its dedupe key, so the operation
    ledger holds no vendor's message id.
    """
    channel, external_id = event.dedupe_key
    blob = "".join(f"{len(part)}:{part}" for part in (channel, external_id))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
    return Intent(principal_id=record.updated_by, intent_ref=f"channel_reply.{digest}")


async def reply_for(
    receipt: Receipt,
    *,
    record: ChannelRecord,
    bindings: ChannelBindings,
    answerer: ChannelAnswerer | None,
    now: datetime,
) -> Outgoing | None:
    """What to send back to an accepted message, or None when nothing on this install answers it.

    A sender bound to nobody is sent the unrecognised prompt and nothing else (M10.3.3). A bound
    sender is the answerer's; with none wired the caller records `not_answerable`.
    """
    if receipt.inbound is None:
        msg = "only an accepted message is replied to"
        raise ValueError(msg)
    event = receipt.inbound.event
    binding = await bindings.binding_for(
        event.channel, identity_hash(event.channel, event.channel_identity)
    )
    if binding is None:
        return Outgoing(
            channel=event.channel,
            to=receipt.reply_to,
            intent=reply_intent(record, event),
            text=Unrecognised(channel=event.channel).prompt,
        )
    if answerer is None:
        return None
    return await answerer.answer(
        receipt.inbound, binding=binding, reply_to=receipt.reply_to, now=now
    )


# ------------------------------------------------------------------------ the claim alone


async def claim(session: AsyncSession, adapter: ChannelAdapter, raw: object) -> Inbound | None:
    """The message as the gate reads it, or None when this channel delivered it before.

    The claim alone, in the caller's transaction, for a caller that already verified and parsed
    what arrived. Normalised first, so a payload the adapter refuses is refused before anything is
    written; claimed second, so the dedupe key is the adapter's own; addressed last. Does not
    commit: the caller owns the transaction, for `first_delivery`'s reason.
    """
    event = adapter.normalise(raw)
    if not await first_delivery(session, event):
        return None
    return Inbound(event=event, address=from_mention(event.text))
