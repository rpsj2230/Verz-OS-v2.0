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
never seen, is known and unbound, or was unbound this morning, and no entitlement at all. On a
process with no database nobody is bound, and `NoBindingsYet` says so rather than guessing; with
one, `brain.ops.binding_store.StoredBindings` answers from `auth.principal_identity`.

**A chat addresses an agent with a mention that opens the message (M3.9.8).**
`brain.gate.addressing.from_mention` takes a leading `@agent_id` off the question, and only a
leading one, for the reason that module gives about quoted text choosing an agent.

**A shared conversation is answered only when a message names the bot (M10.2.6).** A chat whose
wire reads a `brain.channels.adapter.Conversation` says who the message named, by digest; in a
conversation more than one person reads, a message that did not name the bot's own identity is
somebody talking to somebody else, and it is neither answered nor prompted. See
`A_SHARED_CONVERSATION_IS_ANSWERED_ONLY_WHEN_IT_NAMES_THE_BOT`.

**The binding prompt is sent once, to the sender alone (M10.3.3, M1.8.5).** Keyed on the
identity's digest and the record's last change, so a second message from one unbound sender does
not repeat it, and addressed to the sender's own conversation with the bot, so a room is not told
which of its members is unbound. See `THE_BINDING_PROMPT_IS_SENT_ONCE_AND_TO_THE_SENDER_ALONE`.

**A binding code is offered to the binder before the prompt, from a private conversation only
(M1.8.5).** `ChatBinder` is the receiving side of binding: the code is minted in a web session and
redeemed by the store that keeps bindings (CH2's), and nothing here knows its shape. A code posted
where others read it binds nobody. See `A_CODE_IS_REDEEMED_ONLY_WHERE_THE_SENDER_ALONE_READS_IT`.

**A message never decides an approval, on any channel, and the sender is told where one is
decided (M10.7.1).** A bound sender whose message is a decision word, "approve", "reject" and
their kin, or asks for their approvals, is not answered as a question: `reply_for` hands it to the
`ApprovalOfferer` before the answerer, which tells them in words that approvals are decided in the
console, the staff web app or on an approval card, and on a channel that carries cards puts each
approval waiting on them in front of them as one. With no offerer wired it is told the same
sentence alone. Nothing on this path can decide anything: a message is admitted at a binding's
read, and the only decision a chat can take is a press on a card, which is a different request
with its own branch in the events route. The sentence is one for every sender on a channel,
whether or not anything waits on them, so asking cannot learn whether an approval exists. See
`A_MESSAGE_NEVER_DECIDES_AN_APPROVAL`.

**A press on a card is read like a message and handed to the `CardPresser` (M10.2.3).** A wire
that reads one returns `Received.press` beside an event of its own, which `receive` claims as it
claims a message, so a replayed press is refused by the database before anything reads its value.

**A bound sender's address is kept as their message arrives (M10.3.5).** Every accepted message
from a bound sender, and the code that binds one, offers the sender's identity to the
`AddressBook`, which keeps it on the binding it is the fingerprint of where the channel keeps
addresses at all. That is how an approval card can reach a person the moment it is raised
(needs-rupash 118), and how a binding made before addresses were kept gains one: the next time its
person writes.

Task ids: M3.2.2, M3.9.8, M10.2.1, M10.2.6, M10.3.3, M10.6.1, M10.6.3, M1.8.5, M10.7.1, M10.2.3
Task ids: M10.3.5
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from brain.channels.adapter import (
    BOT_ID,
    Arrived,
    CardPress,
    ChannelAdapter,
    ChannelWire,
    Conversation,
)
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

if TYPE_CHECKING:
    from brain.identity.oidc import KeySet

# ------------------------------------------------------------------ written-down reasons

#: Why the order of `receive` is the rule.
A_REQUEST_IS_REFUSED_BEFORE_ITS_BODY_IS_READ: Final = (
    "A channel switched off, or never configured, is refused before a byte of the body is read, "
    "and a request whose signature does not verify is refused before the wire reads the body it "
    "sent. Reading first and refusing after would parse an attacker's bytes on the one path that "
    "exists to refuse them, and a parser is where a crafted body does its work."
)

#: Why nobody is bound on a process with nowhere to keep a binding.
NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT: Final = (
    "A process with no database keeps no channel binding, so no sender is bound to anybody and "
    "every sender is answered as unrecognised. That is the narrow direction: a sender who should "
    "have been answered is told how to bind, and nobody is answered as somebody they are not."
)

#: Why a message in a shared conversation that does not name the bot is left alone.
A_SHARED_CONVERSATION_IS_ANSWERED_ONLY_WHEN_IT_NAMES_THE_BOT: Final = (
    "In a conversation more than one person reads, a message is for the bot only when its "
    "mentions name the bot's own identity, keyed on the vendor's id and never on the text. Any "
    "other message is somebody talking to somebody else, and it is neither answered nor prompted."
)

#: Why the prompt to an unbound sender is keyed on them and addressed to them alone.
THE_BINDING_PROMPT_IS_SENT_ONCE_AND_TO_THE_SENDER_ALONE: Final = (
    "A sender bound to nobody is told how to bind once for each configuration of the channel, "
    "under a key derived from their identity's digest, so a second message does not repeat it; "
    "it goes to the sender's own conversation with the bot, so a room is never told which of its "
    "members is unbound."
)

#: Why a code posted where others read it binds nobody.
A_CODE_IS_REDEEMED_ONLY_WHERE_THE_SENDER_ALONE_READS_IT: Final = (
    "A binding code travels through the channel, so in a shared conversation everybody present "
    "has read it and could present it from their own account first. It is offered to the binder "
    "only from a conversation the sender alone reads; one posted where others read it binds nobody."
)

#: What a sender is told when their code bound this chat to them. Says nothing about anybody else.
LINKED_TOLD: Final = (
    "This chat is now linked to your account. Ask me anything you could ask in the console."
)

#: What a sender is told when a message that was a code bound nothing.
CODE_REFUSED_TOLD: Final = (
    "That code did not link this chat. Codes work once and for ten minutes: make a new one from "
    "your profile in the console and send it here."
)

#: Why a decision word in a message is answered with where to decide, and decides nothing.
A_MESSAGE_NEVER_DECIDES_AN_APPROVAL: Final = (
    "A message is words bound to no action, admitted at a binding's read, so a reply meaning "
    "approve on WhatsApp, email, the webhook channel or a Lark chat decides nothing. The sender "
    "is told, in one sentence the same for everybody, that approvals are decided in the console, "
    "the staff web app or on an approval card; on a channel with cards, each approval waiting on "
    "them is put in front of them as one."
)

#: What a sender whose message was a decision word is told. One sentence for everybody.
DECIDE_WHERE_TOLD: Final = (
    "A message never decides an approval. Approvals are decided on the Approvals screen in the "
    "console or the staff web app, or with the buttons on an approval card in your own Lark chat "
    "with me."
)

#: The words a message opens with when it means to decide something, and the one that asks what
#: is waiting. Closed, and short on purpose: a question that happens to open with one of them is
#: told where to decide rather than answered, which costs a person one more message and never
#: decides anything.
DECISION_WORDS: Final = frozenset(
    {
        "approve",
        "approved",
        "approval",
        "approvals",
        "reject",
        "rejected",
        "decline",
        "declined",
        "deny",
        "denied",
    }
)

#: The most words a decision reply is. Longer is a sentence about something, and a question.
MAX_DECISION_WORDS: Final = 8

#: The largest body read. A chat message with its envelope, never a document: a vendor that
#: sends a file sends a reference to it.
MAX_BODY_BYTES: Final = 256 * 1024


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class Inbound:
    """A message claimed as its first delivery, and what it asks of whom."""

    event: ChannelEvent
    address: Address
    #: Where it was said, for a chat whose conversations can hold more than one reader.
    conversation: Conversation | None = None
    #: A press on a card rather than a message: the events route's `CardPresser` takes it.
    press: CardPress | None = None


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
    """What answers a bound sender: the gate, run as them. `brain.chat_answer.ChatAnswerer`.

    A sequence, because one question in a shared conversation can need more than one message: a
    posting everybody reads, made at their floor, and an aside only the asker reads.
    """

    async def answer(
        self,
        inbound: Inbound,
        *,
        binding: Binding,
        record: ChannelRecord,
        reply_to: str,
        now: datetime,
    ) -> Sequence[Outgoing]:
        """The messages to send, each made at the reach it may be read at and carrying its hash."""
        ...


class Redeemed(enum.StrEnum):
    """What offering a message to the binder came to."""

    #: The message was a live code, and this chat identity is now bound to its minter.
    BOUND = "bound"
    #: The message was a code and binds nobody: wrong, expired or already used.
    REFUSED = "refused"
    #: The message is not a code; it goes on to be answered as an unbound sender's message.
    NOT_A_CODE = "not_a_code"


class ChatBinder(Protocol):
    """Where a chat identity is bound with a single-use code minted in a web session.

    The receiving side of M1.8.5 and M10.3.1: this package hands over the event and what the
    sender typed, and the store that keeps bindings (CH2's `brain.ops.binding_store.StoredBinder`)
    decides whether it is a code, redeems it once through `brain.channels.binding.redeem` and keeps
    the binding. Nothing here knows a code's shape, so the two cannot disagree about it.
    """

    async def redeem(self, event: ChannelEvent, text: str, *, now: datetime) -> Redeemed:
        """Bind this event's sender with the code in `text`, or say why nothing was bound."""
        ...


class AddressBook(Protocol):
    """Where a bound person's own address is kept when a verified event from them arrives.

    `brain.ops.binding_store.StoredAddresses`. Told the channel and the identity the event came
    from, and nothing about what it said; the store decides whether that channel keeps addresses
    and keeps one only on the binding it is the fingerprint of (needs-rupash 118).
    """

    async def remember(self, channel: Channel, identity: str) -> bool:
        """Keep this identity as its binding's address; True when a row changed."""
        ...


class ApprovalOfferer(Protocol):
    """What a bound sender's decision word is answered with. `brain.approval_cards.ApprovalCards`.

    The sentence saying where approvals are decided, first, and on a channel with cards each
    approval waiting on the sender as a card in a conversation only they read. See
    `A_MESSAGE_NEVER_DECIDES_AN_APPROVAL`.
    """

    async def offer(
        self,
        inbound: Inbound,
        *,
        binding: Binding,
        record: ChannelRecord,
        reply_to: str,
        now: datetime,
    ) -> Sequence[Outgoing]:
        """The messages to send: the sentence, then any card, each made at its reader's reach."""
        ...


@dataclass(frozen=True)
class Pressed:
    """What a press on a card came to, as the vendor is answered and the card is then closed.

    `told` is shown to the presser at once and `closed`, when not empty, replaces the card in the
    same answer. `patch` replaces the card after a decision, by a call against the card ceiling,
    and `fallback` is sent only when `patch` was not delivered.
    """

    told: str
    closed: str = ""
    decided: bool = False
    patch: Outgoing | None = None
    fallback: Outgoing | None = None


class CardPresser(Protocol):
    """What decides a press on an approval card. `brain.approval_cards.ApprovalCards`."""

    async def press(
        self, inbound: Inbound, *, record: ChannelRecord, reply_to: str, now: datetime
    ) -> Pressed:
        """Decide this press, or say in one sentence that it decided nothing. `reply_to` is the
        presser's own conversation with the bot, where a fallback goes."""
        ...


def is_decision_reply(text: str) -> bool:
    """Whether a message means to decide an approval, or asks what is waiting (M10.7.1).

    Its first word, a leading slash aside, is one of `DECISION_WORDS`, it is at most
    `MAX_DECISION_WORDS` long, and it is not a question. Read from the words a person typed and
    never from anything they name: which approval they meant is not asked, because no message
    decides one.
    """
    said = text.strip()
    words = said.lower().split()
    if not words or len(words) > MAX_DECISION_WORDS or said.endswith("?"):
        return False
    first = words[0].lstrip("/").strip(".,!:;")
    return first in DECISION_WORDS


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
    keys: Callable[[], Awaitable[KeySet | None]] | None = None,
) -> Receipt:
    """One request to one channel, taken as far as it may go, and recorded however far that is.

    `body` is how the bytes are read, and it is called only once the record is on and the declared
    size is within bounds. `headers` have lower-cased names. Does not answer: a claimed message is
    handed back for `reply_for` and the route. See the module docstring for the order.

    `keys` fetches the vendor's published signing keys for a wire that needs them, and is asked
    only once the secret is held, just before verifying; see
    `brain.channels.adapter.A_PUBLISHED_KEY_IS_FETCHED_BY_THE_ROUTE_AND_JUDGED_BY_THE_WIRE`.
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

    try:
        # What verified is what is read: the same bytes, or, for a vendor that encrypts, the
        # body opened with the secret. Nothing below sees the request as it arrived.
        published = await keys() if keys is not None else None
        arrived = Arrived(headers=headers, body=raw, tenant=record.tenant, keys=published)
        opened = wire.verify(arrived, secret, now)
    except WebhookRefusedError:
        return await _refuse(deliveries, channel, RefusedBecause.BAD_SIGNATURE)
    del secret

    handshake = wire.handshake(opened)
    if handshake is not None:
        return Receipt(kind=ReceiptKind.HANDSHAKE, handshake=handshake)
    return await accept(wire, opened=opened, claims=claims, deliveries=deliveries)


async def accept(
    wire: ChannelWire,
    *,
    opened: Arrived,
    claims: EventClaims,
    deliveries: DeliveryRecords,
) -> Receipt:
    """A request past its checks, read, claimed and recorded: the half of `receive` after verify.

    Its own function for a message that arrives by no request, such as mail
    `brain.mailbox_read` read from a mailbox, whose check is made where it is read; everything
    from reading on is the same for it as for a post, so it is not written twice.
    """
    channel = wire.channel
    try:
        received = wire.read(opened)
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
        inbound=Inbound(
            event=received.event,
            address=from_mention(received.event.text),
            conversation=received.conversation,
            press=received.press,
        ),
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


def prompt_intent(record: ChannelRecord, digest: str) -> Intent:
    """The intent the binding prompt is sent under: one per sender per configuration.

    Keyed on the identity's digest rather than the message, so the operation ledger sends it once
    however many messages the sender writes, and on the record's last change, so a channel set up
    again prompts again. See `THE_BINDING_PROMPT_IS_SENT_ONCE_AND_TO_THE_SENDER_ALONE`.
    """
    version = int(record.updated_at.timestamp() * 1_000_000)
    return Intent(
        principal_id=record.updated_by, intent_ref=f"channel_prompt.{version}.{digest[:32]}"
    )


def names_the_bot(record: ChannelRecord, conversation: Conversation) -> bool:
    """Whether a message in this conversation is for the bot. See the named constant.

    A conversation only its sender reads is for the bot by arriving. A shared one must have named
    the identity the record's `BOT_ID` holds; a record naming no bot answers no shared message,
    which is the narrow direction.
    """
    if not conversation.shared:
        return True
    bot = record.tenant.get(BOT_ID, "")
    return bool(bot) and identity_hash(record.channel, bot) in conversation.addressed


async def reply_for(
    receipt: Receipt,
    *,
    record: ChannelRecord,
    bindings: ChannelBindings,
    answerer: ChannelAnswerer | None,
    now: datetime,
    binder: ChatBinder | None = None,
    offerer: ApprovalOfferer | None = None,
    addresses: AddressBook | None = None,
) -> tuple[Outgoing, ...] | None:
    """What to send back to an accepted message: None when nothing on this install answers it,
    and nothing at all for a shared conversation's message that was not for the bot.

    A sender bound to nobody may be binding: a message in a conversation they alone read is
    offered to `binder` first (M1.8.5). Otherwise they are sent the unrecognised prompt, once and
    to them alone (M10.3.3). A bound sender's own address is offered to `addresses` on every message
    and on the code that binds them, which is how a binding made before addresses were kept gains
    one (M10.3.5). A bound sender's decision word is `offerer`'s, or with none wired is
    told `DECIDE_WHERE_TOLD` alone, in a conversation only they read (M10.7.1). Any other message
    from a bound sender is the answerer's; with none wired the caller records `not_answerable`.
    """
    if receipt.inbound is None:
        msg = "only an accepted message is replied to"
        raise ValueError(msg)
    if receipt.inbound.press is not None:
        msg = "a press on a card is decided by a CardPresser and never replied to as a message"
        raise ValueError(msg)
    inbound = receipt.inbound
    event = inbound.event
    conversation = inbound.conversation
    if conversation is not None and not names_the_bot(record, conversation):
        return ()
    digest = identity_hash(event.channel, event.channel_identity)
    binding = await bindings.binding_for(event.channel, digest)
    if binding is None:
        private = conversation is None or not conversation.shared
        if binder is not None and private:
            redeemed = await binder.redeem(event, event.text.strip(), now=now)
            if redeemed is Redeemed.BOUND and addresses is not None:
                await addresses.remember(event.channel, event.channel_identity)
            if redeemed is not Redeemed.NOT_A_CODE:
                told = LINKED_TOLD if redeemed is Redeemed.BOUND else CODE_REFUSED_TOLD
                return (
                    Outgoing(
                        channel=event.channel,
                        to=receipt.reply_to,
                        intent=reply_intent(record, event),
                        text=told,
                    ),
                )
        return (
            Outgoing(
                channel=event.channel,
                to=receipt.reply_to if conversation is None else conversation.sender_to,
                intent=prompt_intent(record, digest),
                text=Unrecognised(channel=event.channel).prompt,
            ),
        )
    if addresses is not None:
        await addresses.remember(event.channel, event.channel_identity)
    if is_decision_reply(inbound.address.question):
        # Never the answerer's, and never a decision. See `A_MESSAGE_NEVER_DECIDES_AN_APPROVAL`.
        if offerer is not None:
            offered = await offerer.offer(
                inbound, binding=binding, record=record, reply_to=receipt.reply_to, now=now
            )
            return tuple(offered)
        shared = conversation is not None and conversation.shared
        return (
            Outgoing(
                channel=event.channel,
                to=conversation.sender_to if shared and conversation else receipt.reply_to,
                intent=reply_intent(record, event),
                text=DECIDE_WHERE_TOLD,
            ),
        )
    if answerer is None:
        return None
    return tuple(
        await answerer.answer(
            inbound, binding=binding, record=record, reply_to=receipt.reply_to, now=now
        )
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
