"""The one way a message leaves on a channel: switched on, still entitled, carriable, sent once.

Every adapter here has a `send` that renders and checks and appends to a list a test reads, and
none of them reaches a vendor, because a module that opened a socket could not be tested for the
case that matters. What was missing was the step after: the vendor's API, with a credential held
outside configuration, and a record of what the vendor said. `deliver` is that step and it is the
only one, so the rules below are made once for every channel rather than once per adapter.

**The channel's record is read first, and a switched-off channel sends nothing (M10.6.3).** No
record is `not_configured` and a record switched off is `switched_off`, and both are refused before
the secret is borrowed or anything is built. The record is the caller's, read at send time, so a
channel switched off a second ago is off. See `A_SWITCHED_OFF_CHANNEL_SENDS_NOTHING`.

**An answer leaves at the reach its recipient holds when it leaves (M10.4.5).** A message made
for one person and sent later (a queued answer, a task that finished, an approval notice) carries
the hash of the entitlement set it was made at, and the set is loaded again from the store at
send time, not from the cache. A different hash refuses the send as `reach_changed` rather than
re-rendering here: the render is the gate's, and re-running a narrowed answer is the caller's to
do through it. A message for nobody in particular (the prompt to an unbound sender, a test
message) names no recipient, and is refused at construction unless its payload carries nothing
from the company's data. See `AN_ANSWER_LEAVES_AT_THE_REACH_ITS_RECIPIENT_HOLDS_WHEN_IT_LEAVES`.

**The label and the ceiling are checked here and not trusted to the adapter (M10.1.5).**
`brain.channels.adapter.assert_can_send` with the payload's declared classification, then
`brain.channels.cards.assert_label_survives` on the text that will actually be sent. A body that
dropped the opaque label is refused as `cannot_carry` before any request is built.

**The vendor's answer is recorded as what it was, and a refusal is never recorded as sent
(M10.6.1).** `ChannelWire.judge` reads the answer, because a vendor that says 200 with a refusal in
its body is known only to its own wire. Accepted is `sent`; refused, a redirect, a quota or an
unsafe address is `refused`; a silence, a dropped connection or a 5xx is `unknown`, because such a
request may have been delivered and `brain.ops.idempotency.state_after_call` reads it the same way.
Every outcome is written to `ops.channel_delivery` with its reason and the vendor's status and
nothing of the message.

**Sent once, under a key derived from the intent.** The vendor call is made inside
`brain.ops.idempotency.issue_once`, keyed by `adapter.send_operation`, so a retried or raced
delivery posts once. A delivery whose key was already used is answered with what the first
attempt came to and records nothing, because that attempt recorded itself.

Task ids: M10.6.1, M10.6.3, M10.4.5, M10.1.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from brain.channels.adapter import (
    ChannelTransport,
    DeliveryRefusedError,
    VendorAnswer,
    adapter_for,
    assert_can_send,
    channel_wires,
    send_operation,
)
from brain.channels.cards import CardRefusedError, assert_label_survives, render_body
from brain.connectors.throttle import CallOutcome
from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.gate.resolve import EntitlementStore
from brain.ops.channel_store import (
    ChannelRecord,
    ChannelSecrets,
    ChannelSecretsUnavailableError,
    DeliveryEntry,
    DeliveryRecords,
)
from brain.ops.idempotency import (
    Intent,
    Issued,
    Operation,
    OperationLedger,
    OperationState,
    issue_once,
)
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause

# ------------------------------------------------------------------ written-down reasons

#: Why the record is read before anything else.
A_SWITCHED_OFF_CHANNEL_SENDS_NOTHING: Final = (
    "A channel's record is read at send time and a channel switched off, or never configured, is "
    "refused before its secret is borrowed or a request is built, so switching a channel off "
    "stops its sending at once and touches no other channel's record."
)

#: Why a message made for somebody is checked against their reach at send time.
AN_ANSWER_LEAVES_AT_THE_REACH_ITS_RECIPIENT_HOLDS_WHEN_IT_LEAVES: Final = (
    "A message made for one person and sent later carries the hash of the reach it was made at, "
    "and that reach is loaded again from the store when it is sent. A grant revoked in between "
    "changes the hash and the message is refused, so a queued answer can never deliver what its "
    "recipient no longer holds."
)

#: Why a message addressed to nobody in particular may carry nothing from the data.
A_MESSAGE_FOR_NOBODY_IN_PARTICULAR_CARRIES_NOTHING: Final = (
    "A message with no recipient has no reach to be checked against at send time, so its payload "
    "may hold no record and no locked field: it is a product sentence, such as the prompt to an "
    "unbound sender or a test message, and never an answer."
)

#: One pass through the operation ledger, run on the thread the vendor call is made on.
LedgerRunner = Callable[[Callable[[OperationLedger], Issued]], Issued]


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class Outgoing:
    """One message planned for one destination on one channel.

    `text` empty means render the payload. `recipient` and `planned_hash` are both given, for an
    answer made for somebody, or neither, for a product sentence; see the named constants.
    """

    channel: Channel
    to: str
    intent: Intent
    text: str = ""
    payload: ChannelPayload = field(default_factory=ChannelPayload)
    #: The most sensitive classification in the payload, which the channel's ceiling is held to.
    highest: Classification = Classification.INTERNAL
    recipient: str = ""
    planned_hash: str = ""

    def __post_init__(self) -> None:
        if not self.to.strip():
            raise ValueError("a message is sent to somewhere")
        if bool(self.recipient) != bool(self.planned_hash):
            msg = (
                "a message made for somebody names them and the reach it was made at, and a "
                "product sentence names neither"
            )
            raise ValueError(msg)
        if not self.recipient and (self.payload.records or self.payload.locked):
            raise ValueError(A_MESSAGE_FOR_NOBODY_IN_PARTICULAR_CARRIES_NOTHING)


@dataclass(frozen=True)
class Delivered:
    """What one delivery came to. `issued` is False when its key was already used."""

    outcome: DeliveryOutcome
    reason: RefusedBecause | None = None
    vendor_status: int | None = None
    issued: bool = True


def _refused(reason: RefusedBecause, status: int | None = None) -> Delivered:
    return Delivered(outcome=DeliveryOutcome.REFUSED, reason=reason, vendor_status=status)


def _from_answer(answer: VendorAnswer, judged: CallOutcome) -> Delivered:
    """The delivery an answer from the vendor, as its wire judged it, amounts to."""
    if answer.unsafe_address:
        return _refused(RefusedBecause.UNSAFE_ADDRESS)
    if judged is CallOutcome.OK:
        return Delivered(outcome=DeliveryOutcome.SENT, vendor_status=answer.status)
    if judged in (CallOutcome.REJECTED, CallOutcome.QUOTA):
        return _refused(RefusedBecause.VENDOR_REFUSED, answer.status)
    return Delivered(
        outcome=DeliveryOutcome.UNKNOWN,
        reason=RefusedBecause.VENDOR_UNAVAILABLE,
        vendor_status=answer.status,
    )


def _from_earlier(operation: Operation) -> Delivered:
    """What an attempt that already held this key came to, for a caller that asked again."""
    if operation.state is OperationState.SUCCEEDED:
        return Delivered(outcome=DeliveryOutcome.SENT, issued=False)
    if operation.state is OperationState.FAILED:
        return Delivered(
            outcome=DeliveryOutcome.REFUSED, reason=RefusedBecause.VENDOR_REFUSED, issued=False
        )
    return Delivered(
        outcome=DeliveryOutcome.UNKNOWN, reason=RefusedBecause.VENDOR_UNAVAILABLE, issued=False
    )


# ------------------------------------------------------------------------ the send


async def deliver(
    outgoing: Outgoing,
    *,
    record: ChannelRecord | None,
    secrets: ChannelSecrets,
    reach: EntitlementStore,
    transport: ChannelTransport,
    ledger: LedgerRunner,
    deliveries: DeliveryRecords,
    now: datetime,
) -> Delivered:
    """Send one message through its channel's vendor, once, and record what happened.

    Raises `KeyError` for a channel with no wire, because nothing in this release can send on it
    and a caller planning a message there has made a mistake no record would explain.
    """
    delivered = await _attempt(
        outgoing,
        record=record,
        secrets=secrets,
        reach=reach,
        transport=transport,
        ledger=ledger,
        now=now,
    )
    if delivered.issued:
        await deliveries.record(
            DeliveryEntry(
                channel=outgoing.channel,
                direction=Direction.OUTBOUND,
                outcome=delivered.outcome,
                reason=delivered.reason,
                vendor_status=delivered.vendor_status,
            )
        )
    return delivered


async def _attempt(
    outgoing: Outgoing,
    *,
    record: ChannelRecord | None,
    secrets: ChannelSecrets,
    reach: EntitlementStore,
    transport: ChannelTransport,
    ledger: LedgerRunner,
    now: datetime,
) -> Delivered:
    wire = channel_wires()[outgoing.channel]
    if record is None:
        return _refused(RefusedBecause.NOT_CONFIGURED)
    if record.channel is not outgoing.channel:
        msg = f"a {record.channel} record cannot send on {outgoing.channel}"
        raise ValueError(msg)
    if not record.enabled:
        return _refused(RefusedBecause.SWITCHED_OFF)

    if outgoing.recipient:
        # From the store and never the cache: a cached reach is what a revocation a moment ago
        # has not reached yet. See the named constant.
        current = await reach.load(outgoing.recipient, now)
        if current.is_expired(now) or current.ent_hash() != outgoing.planned_hash:
            return _refused(RefusedBecause.REACH_CHANGED)

    text = outgoing.text or render_body(outgoing.payload)
    try:
        assert_can_send(
            adapter_for(outgoing.channel).capabilities(), outgoing.payload, highest=outgoing.highest
        )
        assert_label_survives(text, outgoing.payload)
    except (DeliveryRefusedError, CardRefusedError):
        return _refused(RefusedBecause.CANNOT_CARRY)

    try:
        secret = await asyncio.to_thread(secrets.read, record.secret)
    except ChannelSecretsUnavailableError:
        return _refused(RefusedBecause.VAULT_UNAVAILABLE)
    if secret is None:
        return _refused(RefusedBecause.NO_SECRET)

    try:
        request = wire.request_for(
            to=outgoing.to, text=text, secret=secret, tenant=record.tenant, now=now
        )
    except ValueError:
        return _refused(RefusedBecause.INCOMPLETE)
    del secret

    operation = send_operation(outgoing.intent, channel=outgoing.channel, to=outgoing.to)
    answers: list[tuple[VendorAnswer, CallOutcome]] = []

    def effect(_: Operation) -> CallOutcome:
        answer = transport.send(request)
        judged = wire.judge(answer)
        answers.append((answer, judged))
        return judged

    issued = await asyncio.to_thread(ledger, lambda held: issue_once(held, operation, effect))
    if not issued.issued:
        return _from_earlier(issued.operation)
    answer, judged = answers[0]
    return _from_answer(answer, judged)
