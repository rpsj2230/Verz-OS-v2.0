"""Verifying that a webhook really came from the platform it claims to.

This is the boundary where an anonymous HTTP request becomes a message from a named person.
Everything downstream - binding, entitlement resolution, the whole gate - starts from the
identity in the body, so a forged body is a forged identity, and no amount of care further
in can recover from accepting one.

Four things are checked and each closes a different attack. Getting any of them wrong leaves
the other three looking like they work.

**The signature covers the raw bytes, never the parsed object.** Parse first and you verify
a re-serialisation: JSON has no canonical form, so `{"a":1,"b":2}` and `{"b":2,"a":1}` are
the same object and different bytes, and an attacker who can make the two differ has a body
that verifies as one thing and is read as another. `verify` therefore takes `bytes` and
there is no overload taking a dict.

**The comparison is constant time.** `==` on a digest returns as soon as two bytes differ,
so the time it takes says how much of a guess was right, and a few thousand requests turns
that into the signature. `hmac.compare_digest` exists for this and is not optional.

**A timestamp outside the window is refused.** Without it a signature captured once is valid
for ever, and a request replayed from a proxy log a month later arrives correctly signed.
The window is small and two-sided: a request from the future is as wrong as one from the
past, and only checking one side is the mistake that reads as thorough.

**A nonce is remembered for at least the window.** The timestamp alone bounds a replay to
five minutes rather than preventing it, and five minutes is long enough to resend an
approval. Anything that has already been seen inside the window is refused.

**The company's own system is a channel, and this is its receiver (M10.2.1).** `WIRE` is the
signed webhook mounted: a system of the company's posts a message to
`/api/v1/channels/webhook/events`, signed with the channel's secret over the time and the exact
bytes, and a reply is posted back to the address its record names, signed the same way. It is the
one receiver this release mounts that belongs to no vendor, so the pipeline in
`brain.channels.inbound` and `brain.channels.outbound` is proved on an install before any chat
vendor's receiver is written. Its replay protection is the claim rather than `SeenNonces`: a
replayed request carries the same message id, and `gate.channel_event`'s key refuses it on every
replica, which the in-memory nonces cannot. See `A_REPLAY_IS_REFUSED_BY_THE_CLAIM`.

**Its ceiling is `INTERNAL`.** The answer goes to a system, and that system shows it to whoever
it shows it to: nothing here knows who reads its screens, so the line is the default one and
raising it is a decision somebody makes deliberately, as `brain.channels.lark` says of its own.

Task ids: M10.2.1, M10.1.1, M10.6.1
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from brain.channels.adapter import (
    Arrived,
    ChannelCapabilities,
    Received,
    VendorAnswer,
    VendorRequest,
    assert_can_send,
)
from brain.channels.cards import assert_label_survives, render_body
from brain.connectors.throttle import CallOutcome, classify
from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent

#: How far out of step a request may be. Small, because it bounds how long a captured
#: signature stays useful; not zero, because clocks differ and a strict equality would refuse
#: every request from a machine a second ahead.
DEFAULT_WINDOW = timedelta(minutes=5)


class WebhookRefusedError(Exception):
    """Raised when a request must not be treated as coming from the platform.

    One exception for every reason, and the message never says which check failed in terms
    an attacker could use. "bad signature" and "stale timestamp" and "seen before" tell
    somebody probing which part to fix next, which is the same argument
    `brain.gate.ingress` makes for having one prompt for every unrecognised sender.
    """


@dataclass
class SeenNonces:
    """Nonces seen inside the window, and nothing older.

    In memory, and that is a real limitation stated rather than hidden: two replicas do not
    share this, so a replayed request can be accepted once per replica. Closing that needs
    the shared cache, and this type exists so the seam is visible rather than so the problem
    is solved. The timestamp check still bounds the damage to the window.

    Pruned on write rather than on a timer. A timer is a second thing to run and get wrong,
    and the write path is the only place that can grow this.
    """

    window: timedelta = DEFAULT_WINDOW
    _seen: dict[str, datetime] = field(default_factory=dict)

    def remember(self, nonce: str, now: datetime) -> bool:
        """True if this nonce is new. False means it has been seen inside the window."""
        cutoff = now - self.window
        # Pruned first, so a nonce that has aged out is genuinely forgotten rather than
        # refused for ever - which would make this a growing list of permanent refusals.
        self._seen = {n: at for n, at in self._seen.items() if at > cutoff}
        if nonce in self._seen:
            return False
        self._seen[nonce] = now
        return True

    def __len__(self) -> int:
        return len(self._seen)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The signature the platform would produce for this request.

    Exported so a test can produce a real one rather than asserting against a literal, and
    so the one definition of what is signed lives in one place. The timestamp is inside the
    signed material: signing only the body would let a captured signature be replayed with a
    fresh timestamp, which is the check the timestamp is there to make.
    """
    material = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


def assert_raw_bytes(body: object) -> None:
    """Refuse anything that is not the bytes that arrived.

    Takes `object` rather than `bytes` on purpose. Written inline inside `verify`, whose
    parameter is annotated `bytes`, mypy proves the check dead and asks for it to be
    deleted - and it is very much alive: the caller is a web framework handing over
    whatever arrived, and that untyped call site is the only one an attacker can reach.
    Widening the parameter here makes the check something the type checker can see the
    point of, rather than something suppressed with an ignore comment that the next person
    removes.

    The check itself is the important half. The signature covers the raw bytes, so
    verifying a parsed object verifies something the sender never signed: JSON has no
    canonical form, and an attacker who can make the parse and the re-serialisation differ
    has a body that verifies as one thing and is read as another.
    """
    if not isinstance(body, bytes | bytearray):
        msg = (
            "the signature covers the raw bytes, not a parsed object; verifying a "
            "re-serialisation verifies something the sender never signed"
        )
        raise TypeError(msg)


def verify(
    *,
    secret: str,
    signature: str,
    timestamp: str,
    body: bytes,
    now: datetime,
    nonce: str = "",
    seen: SeenNonces | None = None,
    window: timedelta = DEFAULT_WINDOW,
) -> None:
    """Refuse anything that is not a live, unrepeated request from the platform.

    `body` is bytes and there is deliberately no overload taking a parsed object. Verifying
    a re-serialisation verifies something the sender never signed: JSON has no canonical
    form, so an attacker who can make the parse and the re-serialisation differ has a body
    that verifies as one thing and is read as another.

    Raises rather than returning a bool. A function returning False is one whose result can
    be ignored by writing `verify(...)` on a line by itself, and that line reads as a check.
    """
    assert_raw_bytes(body)

    try:
        sent_at = datetime.fromtimestamp(int(timestamp), tz=now.tzinfo)
    except (ValueError, OverflowError, OSError) as exc:
        raise WebhookRefusedError("this request was not accepted") from exc

    # Two-sided. A request from the future is as wrong as one from the past, and checking
    # only the past is the mistake that reads as thorough: a sender with a fast clock, or an
    # attacker choosing a timestamp, would be accepted for as long as they liked.
    if abs(sent_at - now) > window:
        raise WebhookRefusedError("this request was not accepted")

    expected = sign(secret, timestamp, bytes(body))
    # Constant time. `==` returns as soon as two bytes differ, so the time it takes says how
    # much of a guess was right, and a few thousand requests turn that into the signature.
    if not hmac.compare_digest(expected, signature):
        raise WebhookRefusedError("this request was not accepted")

    if nonce and seen is not None and not seen.remember(nonce, now):
        # The timestamp bounds a replay to the window; this prevents one inside it. Five
        # minutes is long enough to resend an approval.
        raise WebhookRefusedError("this request was not accepted")


def verified_handler[T](
    secret: str,
    parse: Callable[[bytes], T],
    *,
    seen: SeenNonces | None = None,
) -> Callable[[bytes, str, str, str, datetime], T]:
    """Wrap a parser so it cannot be called on an unverified body.

    The shape is the point. A `verify` a caller must remember to call before `parse` is a
    check that goes missing from the one call site somebody adds later; a parser that can
    only be reached through verification cannot be called first. This is the same argument
    `brain.gate.catalogue.ProjectedCatalogue` makes with its constructor token.
    """

    def handle(body: bytes, signature: str, timestamp: str, nonce: str, now: datetime) -> T:
        verify(
            secret=secret,
            signature=signature,
            timestamp=timestamp,
            body=body,
            now=now,
            nonce=nonce,
            seen=seen,
        )
        return parse(body)

    return handle


# ------------------------------------------------ the company's own system (M10.2.1, M10.6.1)

#: Why no nonce is asked of the company's system.
A_REPLAY_IS_REFUSED_BY_THE_CLAIM: Final = (
    "A replayed request carries the message id it was signed with, and the claim on "
    "gate.channel_event refuses a second delivery of one id on every replica. SeenNonces lives "
    "in one process's memory, so on two replicas it refuses a replay once per replica and "
    "accepts it on the other; the claim is the check that holds."
)

#: The headers the time and the signature travel in, as `brain.ops.outbox` names them for the
#: requests this install signs, lower-cased because `Arrived` lower-cases every name. One
#: construction in both directions, so the company's system checks a reply as it signs a message.
TIMESTAMP_HEADER: Final = "x-brain-timestamp"
SIGNATURE_HEADER: Final = "x-brain-signature"

#: The one tenant field this channel needs: where a reply is posted. An https address.
REPLY_URL: Final = "reply_url"

#: The longest identifier or text accepted. A message, not a document.
MAX_ID_CHARS: Final = 255
MAX_TEXT_CHARS: Final = 8000

#: A redirect is a refusal, for `brain.ops.outbox_store.A_REDIRECT_IS_NOT_A_DELIVERY`'s reason.
_REDIRECTS: Final = range(300, 400)


def _field(message: Mapping[str, Any], name: str, *, limit: int, required: bool = True) -> str:
    value = message.get(name, "" if not required else None)
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        msg = f"a message's {name} is a string of at most {limit} characters"
        raise ValueError(msg)
    return value


def normalise_message(raw: object) -> ChannelEvent:
    """A message the company's system sent, as the one shape the gate reads, or `ValueError`.

    `sent_at` is whole seconds since the epoch. The wire puts the signed timestamp there, so the
    instant the gate reads is one the signature vouches for rather than one the body claims.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("a message is a JSON object")
    sent_at = raw.get("sent_at")
    if not isinstance(sent_at, int) or isinstance(sent_at, bool):
        raise ValueError("a message carries sent_at as whole seconds since the epoch")
    return ChannelEvent(
        channel=Channel.WEBHOOK,
        external_id=_field(raw, "id", limit=MAX_ID_CHARS),
        channel_identity=_field(raw, "sender", limit=MAX_ID_CHARS),
        text=_field(raw, "text", limit=MAX_TEXT_CHARS, required=False),
        received_at=datetime.fromtimestamp(sent_at, tz=UTC),
    )


@dataclass(frozen=True)
class WebhookMessage:
    """One message this adapter delivered. What a test reads instead of the company's system."""

    to: str
    body: str


@dataclass
class WebhookAdapter:
    """The company's own system as a surface. No transport, for `LarkAdapter`'s reason.

    `sent` is what a test reads instead of the system; the vendor request is `WIRE`'s to build.
    """

    sent: list[WebhookMessage] = field(default_factory=list)
    reachable: bool = True

    def capabilities(self) -> ChannelCapabilities:
        """Nothing beyond text, and `INTERNAL`: see the module docstring."""
        return ChannelCapabilities(
            channel=Channel.WEBHOOK,
            features=frozenset(),
            max_classification=Classification.INTERNAL,
            can_carry_label=True,
        )

    def normalise(self, raw: object) -> ChannelEvent:
        return normalise_message(raw)

    def send(self, payload: ChannelPayload, *, to: str, body: str = "") -> None:
        """Deliver one payload to one conversation, its label in what is read."""
        assert_can_send(self.capabilities(), payload)
        rendered = body or render_body(payload)
        assert_label_survives(rendered, payload)
        self.sent.append(WebhookMessage(to=to, body=rendered))

    def healthy(self, now: datetime) -> bool:
        del now  # No time-based health; the parameter is the protocol's.
        return self.reachable


@dataclass(frozen=True)
class SignedWebhookWire:
    """`brain.channels.adapter.ChannelWire` for the company's own system. Holds no secret."""

    @property
    def channel(self) -> Channel:
        return Channel.WEBHOOK

    @property
    def tenant_fields(self) -> tuple[str, ...]:
        return (REPLY_URL,)

    def verify(self, arrived: Arrived, secret: str, now: datetime) -> None:
        """`verify` over the exact bytes, the signed time and the signature, and nothing read."""
        verify(
            secret=secret,
            signature=arrived.headers.get(SIGNATURE_HEADER, ""),
            timestamp=arrived.headers.get(TIMESTAMP_HEADER, ""),
            body=arrived.body,
            now=now,
        )

    def handshake(self, arrived: Arrived) -> Mapping[str, str] | None:
        """The company's system does not check an address before it posts, so never."""
        del arrived
        return None

    def read(self, arrived: Arrived) -> Received:
        """The verified body as a message, at the time its signature covers."""
        try:
            parsed = json.loads(arrived.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("a message is a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("a message is a JSON object")
        signed = int(arrived.headers.get(TIMESTAMP_HEADER, ""))
        event = normalise_message({**parsed, "sent_at": signed})
        conversation = _field(parsed, "conversation", limit=MAX_ID_CHARS, required=False)
        return Received(event=event, reply_to=conversation or event.channel_identity)

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        """A reply, signed as a message is, posted to the record's reply address."""
        url = tenant.get(REPLY_URL, "")
        if not url.startswith("https://"):
            msg = f"this channel's record names no https {REPLY_URL} to post a reply to"
            raise ValueError(msg)
        body = json.dumps({"text": text, "to": to}, separators=(",", ":"), sort_keys=True)
        encoded = body.encode("utf-8")
        timestamp = str(int(now.timestamp()))
        return VendorRequest(
            url=url,
            headers={
                TIMESTAMP_HEADER: timestamp,
                SIGNATURE_HEADER: sign(secret, timestamp, encoded),
            },
            body=encoded,
        )

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        """A 2xx is delivered, a redirect or an unsafe address is refused, and the rest is
        `brain.connectors.throttle.classify`'s."""
        if answer.unsafe_address or (answer.status is not None and answer.status in _REDIRECTS):
            return CallOutcome.REJECTED
        return classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed,
        )


#: This channel's wire, found by `brain.channels.adapter.channel_wires`.
WIRE: Final = SignedWebhookWire()
