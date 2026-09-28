"""Lark: how a message is read, and who is allowed to read the answer.

Lark is the channel most of the company will actually use, and it is the one where the
audience is not the asker. Everything difficult here follows from that.

**A group chat has more than one reader and the answer was computed for one caller.**
`channels.room.floor` already computes the intersection of everyone present, and
`channels.room.plan` decides how far an answer had to fall back. What was missing is the
step after: turning that decision into concrete messages without the asker's answer being
one of them. So a room posting carries the payload computed at the floor, a per-viewer body
is delivered ephemerally to one person, and `_assert_room_only_carries_the_floor` refuses a
plan where anything going to the room was computed at any other reach. Posting the asker's
full answer into a room and hoping nobody else reads it is the failure this module exists to
prevent, and it is invisible in a diff: the message looks like every other message.

**The floor check is on the way out, not on the way in.** The rejected design checked the
caller's `room_body` against the floor as it arrived. That misses the bug that actually
happens, which is not a mislabelled input but the asker's payload reaching the room posting
one branch later. Checking every delivery that is about to go to the room catches both, so
there is one enforcement point rather than two that look like two and are really one.

**A mention is attacker-influenced text and the stable id is not.** Lark puts display names
in the message body: a person can rename themselves after a colleague, or simply type
`@Brain` and `@_user_1` into their own text. A parser that read the rendered text would let
either of those address the bot on somebody else's behalf. `Mention` therefore carries the
placeholder key and the salted hash of the open id, and deliberately **has no display-name
field at all**: a name held on the object is a name somebody eventually compares on.
`gate.ingress.identity_hash` is the hash, reused rather than reimplemented, so a mention and
a binding agree about what an identity is.

**Nobody is addressed by their raw channel identity.** A `Delivery` names a viewer by
`identity_hash` and refuses anything that is not one. An open id in a delivery is an open id
one interpolation away from a message body, and `gate.ingress.Binding` makes the same choice
for the same reason: a table of them is a phone book of the company.

**A direct message and a group message take different paths on purpose.** They could share
one, with a one-member room, and `room.plan` would return FULL and the right answer. It was
rejected because the two differ in what a mistake costs. A p2p chat has exactly one reader
and the answer is theirs; a group has readers nobody asked the gate about. Sharing a path
means one edit changes both, and the edit that widens the group is the one nobody sees. The
direct path here also refuses a p2p chat carrying more than the asker, which is the wiring
fault that would otherwise turn a group into a one-member room.

Nothing here opens a connection and there is no SDK. The event shape is data: `normalise`
accepts the mapping Lark posts, refuses anything it cannot read, and produces the same
`gate.ingress.ChannelEvent` every other channel produces. A module that owned an HTTP client
could not be tested for the case that matters, which is a group message rendered at the
wrong reach.

**`WIRE` is Lark on the one events address, and it trusts nothing it has not opened.** Lark
signs an event with the app's Encrypt Key over the time, a nonce and the exact bytes, encrypts
the body with the same key, and puts the Verification Token inside it. `verify_event` checks the
signature over the bytes before anything is decrypted, opens the body, and compares the token in
constant time; a body that is not encrypted is refused, so the one downgrade an attacker holding
neither key could try is closed. Lark's address check, the `url_verification` challenge, is the
one request that may arrive unsigned, and it is answered only when it decrypts under the key and
carries the token, and it causes nothing but its own echo. See
`AN_EVENT_IS_SIGNED_ENCRYPTED_AND_TOKENED_OR_REFUSED`. The algorithm is Lark's own server SDK's
(`larksuite/oapi-sdk-python`, `lark_oapi/event/dispatcher_handler.py` and
`lark_oapi/core/utils/decryptor.py`) and the decryption is held to the worked example in Lark's
event subscription documentation, "test key" opening to "hello world".

**Every reply is sent with a token minted for it.** Lark authorises a send with a tenant access
token exchanged for the App ID and App Secret, so `request_for` builds the send and hands the
exchange beside it as a `TokenExchange`; the transport makes the two back to back and keeps the
token nowhere. A room posting, a direct message and a per-viewer card are three addresses in one
`to` string, so the operation ledger keys each separately: `chat:`, `user:` and `aside:`. The
shapes are the vendor's documented ones as a generated SDK records them (`chyroc/lark`,
`api_message_send.go`, `api_message_send_ephemeral.go`, `api_chat_member_get_list.go`,
`api_bot_info.go`), and `judge` reads Lark's `code`, which is where it refuses inside a 200.

Task ids: M10.2.2, M10.2.5, M10.2.6, M10.2.1, M10.6.1
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, assert_never
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from brain.channels.adapter import (
    BOT_ID,
    Arrived,
    ChannelCapabilities,
    Conversation,
    DeliveryRefusedError,
    Feature,
    Received,
    TokenExchange,
    VendorAnswer,
    VendorRequest,
    assert_can_send,
    send_operation,
)
from brain.channels.cards import assert_label_survives, render_body
from brain.channels.room import Degradation, Member, plan
from brain.channels.webhook import WebhookRefusedError, assert_raw_bytes
from brain.connectors.staff_directories import LARK_PLATFORMS
from brain.connectors.throttle import CallOutcome, classify
from brain.core.field_policy import Classification
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent, identity_hash
from brain.ops.idempotency import Intent, Issued, Operation, OperationLedger, issue_once

# ------------------------------------------------------------------ written-down reasons

#: Why a mention is resolved by open id and never by the name beside it.
#:
#: The display name is chosen by the person and rendered into the message text, so it is
#: attacker-influenced twice over: somebody can rename themselves after a colleague, and
#: somebody can type another person's name into their own message. The open id is issued by
#: the tenant and appears in a structured field the sender does not author.
MENTIONS_ARE_KEYED_ON_THE_STABLE_ID: Final = (
    "a mention is resolved by the platform's own identifier, never by the rendered name; a "
    "parser that trusted display names lets somebody name themselves after a colleague"
)

#: Why everything posted where more than one person reads it is built at the floor.
A_ROOM_IS_ANSWERED_AT_ITS_FLOOR: Final = (
    "a message everybody in the room can read is built at the intersection of what everybody "
    "in the room holds; the asker's reach decides what the asker sees privately and never "
    "what a colleague reads"
)

#: Why a viewer is named by hash.
A_VIEWER_IS_NAMED_BY_HASH: Final = (
    "a delivery addresses a person by the salted digest of their channel identity; a raw "
    "open id in a delivery is one interpolation away from being in a message body"
)

#: A sha256 hexdigest, the shape `gate.ingress.identity_hash` produces.
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")

#: What a fully installed Lark app can do. The default for `LarkAdapter.features`, and not
#: a floor: an installation granted fewer scopes declares fewer, which is why the adapter
#: carries this as a field rather than returning it from a constant method.
#:
#: `STREAMING` is absent deliberately. Lark can update a card as tokens arrive, and doing so
#: costs one patch per update against the ceiling `channels.cards` budgets; declaring the
#: feature before that budget has been sized for it would spend the close reserve on
#: cosmetics.
LARK_FEATURES: Final[frozenset[Feature]] = frozenset(
    {Feature.EPHEMERAL, Feature.CARDS, Feature.EDIT_IN_PLACE, Feature.ATTACHMENTS}
)

#: The one message type this normaliser reads. Others are refused rather than guessed at:
#: an image, a file or a card action is a different event with a different shape, and
#: pretending an empty string is its text would put a blank question through the gate.
TEXT_MESSAGE: Final = "text"


class LarkRefusedError(Exception):
    """Raised when a Lark event cannot be read, or an answer cannot be planned for one.

    Not a `BrainError`, for the reason `adapter.DeliveryRefusedError` gives about itself: a
    malformed event and a mis-built plan are wiring faults rather than outcomes of somebody's
    question, and degrading them into an answer hides a bug behind a shrug.
    """


# ---------------------------------------------------------------- chat shape (M10.2.6)


class ChatType(enum.StrEnum):
    """Lark's own two words for who is in a conversation. Closed, and checked closed.

    The values are the vendor's (`p2p`, `group`) rather than ours, so the wire shape needs no
    translation table that could drift. `audience_is_one_person` is where a third member
    would have to be given an answer, and `assert_never` makes adding one without that
    answer a type error rather than a default.
    """

    DIRECT = "p2p"
    GROUP = "group"


def audience_is_one_person(chat: ChatType) -> bool:
    """Whether the only reader is the person who asked.

    The declaration every chat type has to make, in the shape `gate.context.traffic_class_for`
    makes it. A dictionary with a default would accept a new chat type silently, and the
    default that reads as safe (`False`, treat it as a group) is the one that would answer a
    private question at a floor nobody is standing on.
    """
    match chat:
        case ChatType.DIRECT:
            return True
        case ChatType.GROUP:
            return False
        case _:
            assert_never(chat)


# ------------------------------------------------------------------ mentions (M10.2.2)


@dataclass(frozen=True)
class Mention:
    """One person named in a message. A placeholder key and a stable identity, and no name.

    **There is deliberately no `display_name` field.** See
    `MENTIONS_ARE_KEYED_ON_THE_STABLE_ID`. Keeping the name "for rendering" is how it ends up
    in a comparison: the first time somebody wants to reply "@Wei Ling, here is that figure",
    the name is on the object and the shortest route to it is the one that gets written.
    Rendering a mention back is the vendor's job through the placeholder key, which is what
    the key is for.

    `identity` is `gate.ingress.identity_hash`, salted per channel. Reused rather than
    recomputed here so a mention and a binding cannot disagree about who somebody is.
    """

    #: The token that stands in for this person inside the message text (`@_user_1`).
    key: str
    #: The salted digest of the platform's own identifier for them.
    identity: str


@dataclass(frozen=True)
class LarkMessage:
    """One inbound message, normalised, with the Lark-shaped extras the gate does not carry.

    `event` is the shape every other channel produces, so everything downstream reads one
    type. The extras beside it are the ones a chat has and an email does not: which
    conversation this is, whether more than one person is in it, and who was named.
    """

    event: ChannelEvent
    chat_id: str
    chat_type: ChatType
    mentions: tuple[Mention, ...] = ()

    @property
    def sender_identity(self) -> str:
        """The salted digest of the sender's channel identity.

        Derived rather than stored, so it cannot be set to somebody else's while the event
        beside it says otherwise.
        """
        return identity_hash(self.event.channel, self.event.channel_identity)


def _mapping(node: object, what: str) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        msg = f"{what} is {type(node).__name__} and not an object; this is not a Lark event"
        raise LarkRefusedError(msg)
    return node


def _text(node: Mapping[str, Any], key: str, what: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value:
        msg = f"{what} has no {key}; a Lark event without one cannot be read"
        raise LarkRefusedError(msg)
    return value


def _received_at(header: Mapping[str, Any]) -> datetime:
    """Lark's `create_time`, which is milliseconds since the epoch as a string.

    Converted here rather than passed through, because `ChannelEvent.received_at` is a
    datetime for every channel and a channel that handed over a string would make every
    downstream comparison a per-channel special case.
    """
    raw = _text(header, "create_time", "the event header")
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        msg = f"event create_time {raw!r} is not a millisecond timestamp"
        raise LarkRefusedError(msg) from exc


def _mention(raw: object, index: int) -> Mention:
    """One mention, keyed on the open id and refusing one without it.

    Refused rather than skipped. A mention we cannot key on a stable id is one that could
    only be resolved by the name beside it, and silently dropping it makes a message that
    *did* address the bot read as one that did not, which is a denial somebody can cause on
    purpose by sending a malformed mention.
    """
    node = _mapping(raw, f"mention {index}")
    identifiers = _mapping(node.get("id"), f"mention {index} id")
    open_id = _text(identifiers, "open_id", f"mention {index}")
    return Mention(
        key=_text(node, "key", f"mention {index}"),
        identity=identity_hash(Channel.LARK, open_id),
    )


def normalise_message(raw: object) -> LarkMessage:
    """The mapping Lark posts, as one internal shape (M10.2.2).

    The shape accepted is stated here rather than inferred from whatever arrives: header,
    event, sender open id, message id, chat id, chat type, message type and content. Anything
    missing is refused, because the alternative is a default, and the defaults available are
    all worse than a refusal: an empty text is a blank question through the gate, an absent
    chat type is a group answered as a direct message or the reverse.

    **The text is taken from `content` and the mentions from `mentions`, and the two are
    never crossed.** The content is what the sender typed, placeholders and all; a sender can
    put `@_user_1` or a colleague's name in it. Only the structured `mentions` array carries
    identifiers the tenant issued, so it is the only thing `addressed_to` reads.
    """
    envelope = _mapping(raw, "the event")
    header = _mapping(envelope.get("header"), "the event header")
    body = _mapping(envelope.get("event"), "the event body")
    sender = _mapping(body.get("sender"), "the sender")
    sender_id = _mapping(sender.get("sender_id"), "the sender id")
    message = _mapping(body.get("message"), "the message")

    message_type = _text(message, "message_type", "the message")
    if message_type != TEXT_MESSAGE:
        msg = (
            f"this normaliser reads {TEXT_MESSAGE!r} messages and this one is "
            f"{message_type!r}; a different shape read as text is a blank question"
        )
        raise LarkRefusedError(msg)

    raw_content = _text(message, "content", "the message")
    try:
        content = _mapping(json.loads(raw_content), "the message content")
    except json.JSONDecodeError as exc:
        msg = "the message content is not JSON; Lark encodes it as a JSON string"
        raise LarkRefusedError(msg) from exc
    said = content.get("text")
    if not isinstance(said, str):
        msg = "the message content has no text; a Lark event without one cannot be read"
        raise LarkRefusedError(msg)

    chat_type = _text(message, "chat_type", "the message")
    try:
        chat = ChatType(chat_type)
    except ValueError as exc:
        msg = (
            f"chat type {chat_type!r} is neither {ChatType.DIRECT.value!r} nor "
            f"{ChatType.GROUP.value!r}; whether more than one person reads this decides "
            "what may be said in it"
        )
        raise LarkRefusedError(msg) from exc

    mentions = message.get("mentions") or ()
    if not isinstance(mentions, Sequence) or isinstance(mentions, str | bytes):
        msg = "the message mentions is not a list; a mention cannot be read from a string"
        raise LarkRefusedError(msg)

    return LarkMessage(
        event=ChannelEvent(
            channel=Channel.LARK,
            external_id=_text(message, "message_id", "the message"),
            channel_identity=_text(sender_id, "open_id", "the sender"),
            text=question_of(said, mentions),
            received_at=_received_at(header),
        ),
        chat_id=_text(message, "chat_id", "the message"),
        chat_type=chat,
        mentions=tuple(_mention(item, index) for index, item in enumerate(mentions)),
    )


#: A mention's placeholder as Lark writes it into the text.
_PLACEHOLDER: Final = re.compile(r"@_user_\d+")


def question_of(said: str, mentions: Sequence[object]) -> str:
    """What the sender asked: their words with Lark's placeholders made readable (M10.2.2).

    Placeholders that open the message say who it is for and are removed, so `@Brain what is
    left on SNM` asks what is left on SNM. One later in the text names somebody the question is
    about and becomes the name Lark rendered for it. **The name is words in a question and
    decides nothing**: who the message was addressed to is read from the ids alone, as
    `MENTIONS_ARE_KEYED_ON_THE_STABLE_ID` says, and a person who renames themselves changes only
    the wording of their own question. A placeholder no mention names is left as typed.
    """
    names = {
        str(node.get("key")): str(node.get("name") or "")
        for node in mentions
        if isinstance(node, Mapping) and isinstance(node.get("key"), str)
    }
    text = said.strip()
    while True:
        opening = _PLACEHOLDER.match(text)
        if opening is None or opening.group(0) not in names:
            break
        text = text[opening.end() :].lstrip()
    return _PLACEHOLDER.sub(lambda one: names.get(one.group(0)) or one.group(0), text).strip()


def addressed_to(message: LarkMessage, *, identity: str) -> bool:
    """Whether this message named that identity (M10.2.2).

    Reads `mentions` and never `event.text`. See `MENTIONS_ARE_KEYED_ON_THE_STABLE_ID`: the
    text contains whatever the sender typed, so a message whose words say `@Brain` has not
    addressed the bot, and a message whose words say nothing of the sort has, if the tenant
    put the bot's open id in the structured field.
    """
    return any(mention.identity == identity for mention in message.mentions)


def should_answer(message: LarkMessage, *, bot_identity: str) -> bool:
    """Whether the bot has been spoken to (M10.2.6).

    A direct message is addressed by arriving: there is nobody else in the conversation to
    have meant it for. In a group it has to be a mention, because answering everything in a
    room is a bot that reads a colleague's question about a client and answers it to the
    room at a floor nobody asked it to compute.
    """
    return audience_is_one_person(message.chat_type) or addressed_to(message, identity=bot_identity)


# ------------------------------------------------------- delivery (M10.2.5, M10.2.6)


class Visibility(enum.StrEnum):
    """Who will read one message. Closed, because each member is a different guarantee."""

    #: Everybody in the chat. Built at the floor, always.
    ROOM = "room"
    #: One named person, in a chat other people are in. The mechanism that lets somebody see
    #: more than the floor without the floor moving.
    EPHEMERAL = "ephemeral"
    #: A one-to-one chat, where the only reader is the person who asked.
    DIRECT = "direct"


@dataclass(frozen=True)
class Rendered:
    """A payload and the reach it was computed at.

    The pair travels together for the reason `gate.context.GateContext` keeps its own pair
    together: a payload separated from the reach it was computed at is one that can be
    posted anywhere, and the mistake looks like a variable name.
    """

    payload: ChannelPayload
    #: `EntitlementSet.ent_hash` of the reach the gate used. A claim by the caller, checked
    #: against the floor this module computes for itself.
    ent_hash: str


@dataclass(frozen=True)
class Delivery:
    """One message, to one place, with one audience.

    The invariants are on the type rather than in the planner, because a `Delivery` is also
    built by hand in a test and by whatever wires this to the SDK later, and an invariant
    that only the planner applies is one the second caller does not have.
    """

    chat_id: str
    visibility: Visibility
    payload: ChannelPayload
    #: The reach `payload` was computed at.
    ent_hash: str
    degradation: Degradation
    #: The viewer, as a salted digest. Empty for a room posting.
    to_identity: str = ""

    def __post_init__(self) -> None:
        if not self.chat_id:
            msg = "a delivery with no chat has nowhere to go"
            raise LarkRefusedError(msg)
        if self.visibility is Visibility.ROOM:
            if self.to_identity:
                # A room posting addressed to one person is a contradiction that resolves
                # the wrong way on every surface: the address is advisory and the posting is
                # public, so it reads as private and is read by everybody.
                msg = (
                    "a room posting names a viewer; it would read as private and be posted "
                    "publicly. A per-viewer body is EPHEMERAL or it is not sent"
                )
                raise LarkRefusedError(msg)
            return
        if not _DIGEST_RE.match(self.to_identity):
            msg = (
                f"{self.visibility} delivery names {self.to_identity!r} as its viewer. "
                f"{A_VIEWER_IS_NAMED_BY_HASH}"
            )
            raise LarkRefusedError(msg)


@dataclass(frozen=True)
class DeliveryPlan:
    """Everything that will be sent for one question, and how far it had to fall back.

    `degradation` is carried up from `room.plan` rather than recomputed, so a trace can say
    why somebody got a link instead of an answer without this module having its own opinion
    about which of the four happened.
    """

    deliveries: tuple[Delivery, ...]
    degradation: Degradation
    #: Where the gate can run again for whoever follows it. Set when nothing is posted here,
    #: and required then, since silence is not one of the outcomes; and set beside a room
    #: posting the asker holds more than, where the surface has no private way to say the rest.
    link: str = ""


def _assert_room_only_carries_the_floor(deliveries: Sequence[Delivery], floor_hash: str) -> None:
    """The single enforcement point for `A_ROOM_IS_ANSWERED_AT_ITS_FLOOR` (M10.4.1, M10.2.6).

    Asked of what is about to be sent rather than of what arrived. Checking the caller's
    `room_body` on the way in reads as the same check and is weaker: it passes while the
    asker's payload is assigned to the room posting one branch later, which is the mistake
    that actually happens. Everything with `Visibility.ROOM` is checked here, so both the
    mislabelled input and the misrouted body are refused by one condition.

    It cannot catch a caller who hands over the asker's payload while claiming the floor's
    hash. Nothing can: the hash is a claim about work this module did not do. What it does
    catch is every case where the claim and the destination disagree, which is what a
    channel is in a position to know.
    """
    for delivery in deliveries:
        if delivery.visibility is Visibility.ROOM and delivery.ent_hash != floor_hash:
            msg = (
                f"a room posting was computed at {delivery.ent_hash!r} and this room's floor "
                f"is {floor_hash!r}. {A_ROOM_IS_ANSWERED_AT_ITS_FLOOR}"
            )
            raise LarkRefusedError(msg)


def plan_delivery(
    message: LarkMessage,
    *,
    members: Sequence[Member],
    asker_id: str,
    capabilities: ChannelCapabilities,
    room_body: Rendered | None,
    asker_body: Rendered,
    now: datetime,
    link: str = "",
) -> DeliveryPlan:
    """What to send for one question, to whom, and at whose reach (M10.2.5, M10.2.6).

    Two paths, and they are separate on purpose; see the module docstring. The direct path
    answers the one person in the conversation at their own reach. The group path asks
    `room.plan` for the floor and the degradation, posts the floor to the room, and delivers
    the asker's own body ephemerally when there is more of it and the surface can do that.

    The viewer of an ephemeral delivery is derived from the event rather than passed in.
    `message.sender_identity` is the person who asked, and taking it from the message means
    the private body cannot be addressed to somebody the message did not come from.

    `room_body` and `asker_body` are computed by the gate and handed over. Nothing here
    redacts or intersects: that is the gate's work, and a channel doing it again would be a
    second opinion whose permissive half wins the day the two disagree.

    **A floor that holds nothing posts nothing to the room**, whatever `room_body` says: an
    answer made at no reach at all is an abstention in front of everybody, and the asker's own
    body goes to them alone. `room_body` None says the caller has nothing worth posting at the
    floor; where the asker has no aside either, that is the link. `FLOOR_ONLY` carries the link
    beside the room posting, because the room's answer is all the surface can say and the asker
    holds more: the ladder ends where the gate runs again for them (M10.4.3).
    """
    if audience_is_one_person(message.chat_type):
        present = frozenset(member.principal_id for member in members)
        if present != {asker_id}:
            # A p2p chat carrying anybody but the asker is a group that arrived mislabelled,
            # and answering it on this path would answer it at one person's reach in front
            # of the others. Refused rather than promoted to the group path: the two
            # descriptions of the same chat disagree, and picking one is a guess.
            msg = (
                f"this {ChatType.DIRECT.value} chat lists {len(present)} members and the "
                f"asker is {asker_id}; a direct chat with anybody else in it is a group"
            )
            raise LarkRefusedError(msg)
        deliveries = (
            Delivery(
                chat_id=message.chat_id,
                visibility=Visibility.DIRECT,
                payload=asker_body.payload,
                ent_hash=asker_body.ent_hash,
                degradation=Degradation.FULL,
                to_identity=message.sender_identity,
            ),
        )
        # No floor sweep on this path, and that is not an omission. There is no room
        # posting to sweep: a p2p chat has one reader, the check above has proved it is the
        # asker, and running a sweep over deliveries none of which are `ROOM` would read as
        # an enforcement point while enforcing nothing.
        return DeliveryPlan(deliveries=deliveries, degradation=Degradation.FULL)

    render = plan(members, asker_id, capabilities, now=now)
    floor_hash = render.envelope.ent_hash()

    if render.degradation is Degradation.LINK_ONLY:
        if not link:
            # Nothing may be said and there is nowhere to send them. Saying nothing at all
            # leaves somebody waiting on an answer that is never coming, and the honest
            # alternative to an answer is a place the gate runs again for whoever follows it.
            msg = (
                "nothing may be said in this room and no link was offered; a question with "
                "no answer and no route is silence, which is not one of the outcomes"
            )
            raise LarkRefusedError(msg)
        return DeliveryPlan(deliveries=(), degradation=render.degradation, link=link)

    floor_holds_something = bool(render.envelope.grants) and not render.envelope.is_expired(now)
    built = (
        [
            Delivery(
                chat_id=message.chat_id,
                visibility=Visibility.ROOM,
                payload=room_body.payload,
                ent_hash=room_body.ent_hash,
                degradation=render.degradation,
            )
        ]
        if room_body is not None and floor_holds_something
        else []
    )

    # `render.aside_for` rather than a comparison of the two reaches, and rather than a
    # second check that this surface can do ephemeral messages. `room.plan` sets it only for
    # a surface that supports the feature, so repeating the question here would be a branch
    # nothing can reach: two enforcement points that are really one, which is worse than one
    # because the next person to edit this deletes whichever they find first. The check that
    # a per-viewer send is honourable belongs to the adapter, which is where it is.
    if render.aside_for:
        built.append(
            Delivery(
                chat_id=message.chat_id,
                visibility=Visibility.EPHEMERAL,
                payload=asker_body.payload,
                ent_hash=asker_body.ent_hash,
                degradation=render.degradation,
                to_identity=message.sender_identity,
            )
        )

    planned = tuple(built)
    _assert_room_only_carries_the_floor(planned, floor_hash)
    if not planned and not link:
        msg = (
            "nothing was worth posting in this room, the asker has no aside and no link was "
            "offered; a question with no answer and no route is silence"
        )
        raise LarkRefusedError(msg)
    if render.degradation is Degradation.FLOOR_ONLY or not planned:
        return DeliveryPlan(deliveries=planned, degradation=render.degradation, link=link)
    return DeliveryPlan(deliveries=planned, degradation=render.degradation)


# ------------------------------------------------------------------------- the adapter


@dataclass(frozen=True)
class SentMessage:
    """One message this adapter delivered. What a test reads instead of a Lark tenant."""

    chat_id: str
    body: str
    #: The viewer of an ephemeral message, as a digest. Empty when everybody in the chat
    #: reads it.
    viewer: str = ""


@dataclass
class LarkAdapter:
    """The Lark surface, with the transport left out on purpose.

    There is no client here and no credentials. The vendor's SDK belongs on the other side
    of `sent`, and keeping it there is what makes the case that matters testable: a group
    message rendered at the wrong reach is a bug in the planning, and a module that opened a
    socket could only be tested for it with a Lark tenant standing by.

    `reachable` is what `healthy` answers. A flag rather than a probe, for the reason
    `adapter.ChannelAdapter.healthy` gives: configured-and-unreachable and never-set-up send
    a person to different places, and this type has to be able to express the first.

    `features` is a field rather than a constant because it is genuinely per tenant. What a
    Lark app may do depends on the scopes it was granted when somebody installed it, and an
    installation without the ephemeral scope is a real configuration rather than a
    hypothetical one. An adapter that could not express it would answer `EPHEMERAL` and then
    fail on the wire, which is a private body posted where everybody reads it.
    """

    sent: list[SentMessage] = field(default_factory=list)
    reachable: bool = True
    features: frozenset[Feature] = LARK_FEATURES

    def capabilities(self) -> ChannelCapabilities:
        """What this installation can do, declared rather than inferred.

        `CONFIDENTIAL` and not `RESTRICTED`, and that half is not configurable. Lark is
        behind the tenant and the identity provider, which is why it carries more than
        WhatsApp does; it is also a chat client installed on personal phones with history,
        search and export, which is why the most sensitive class stays in the console.
        Raising that line is a decision somebody makes deliberately, not something an
        adapter infers from having a card renderer.
        """
        return ChannelCapabilities(
            channel=Channel.LARK,
            features=self.features,
            max_classification=Classification.CONFIDENTIAL,
            can_carry_label=True,
        )

    def normalise(self, raw: object) -> ChannelEvent:
        """Whatever arrived, as the one shape the gate reads."""
        return normalise_message(raw).event

    def send(
        self,
        payload: ChannelPayload,
        *,
        to: str,
        body: str = "",
        viewer: str = "",
        ephemeral: bool = False,
    ) -> None:
        """Deliver one payload into one chat (M10.2.5).

        `body` empty means render the payload. It was the one adapter here whose send could
        not carry a composed body, which made it the one surface nobody could correct an
        answer from once `brain.channels.correction` put that line into the body (M34.2.2.1).
        Whichever it is, the produced string is checked against the payload's label, the check
        every other adapter already made.

        `viewer` empty means everybody in `to` reads it. A viewer named means only they do,
        and that is refused unless this surface actually supports it: an ephemeral message
        sent to a channel that cannot do ephemeral messages is a private answer posted into
        a room, which is the failure `adapter.Feature.EPHEMERAL` exists to name.

        `ephemeral` is stated separately from `viewer` being set, so that asking for a
        per-viewer message and forgetting the viewer is a refusal rather than a public post.

        `assert_can_send` runs first and is not restated here, so this adapter cannot
        disagree with any other about labels and classifications.
        """
        assert_can_send(self.capabilities(), payload)
        if ephemeral != bool(viewer):
            msg = (
                "an ephemeral send names its viewer and a public one names none; the two "
                "disagree here, and the resolution that reads as safe is the public one"
            )
            raise DeliveryRefusedError(msg)
        if viewer and not self.capabilities().supports(Feature.EPHEMERAL):
            msg = (
                f"{Channel.LARK} cannot send a per-viewer message, so this body would be "
                "posted where everybody in the chat reads it"
            )
            raise DeliveryRefusedError(msg)
        rendered = body or render_body(payload)
        assert_label_survives(rendered, payload)
        self.sent.append(SentMessage(chat_id=to, body=rendered, viewer=viewer))

    def healthy(self, now: datetime) -> bool:
        """Whether this adapter can currently deliver. See `adapter.registered`."""
        del now  # No time-based health here; the parameter is the protocol's.
        return self.reachable


def deliver(
    adapter: LarkAdapter, delivery: Delivery, *, ledger: OperationLedger, intent: Intent
) -> Issued:
    """Send one planned delivery, once (M17.3.1).

    The mapping from a `Visibility` to a send is here rather than on the adapter, so that
    `LarkAdapter.send` keeps the signature `redaction.assert_channel_adapter` can check: a
    parameter typed `Delivery` names no `ChannelPayload`, and an adapter that took one could
    not be shown safe by reading it.
    """
    ephemeral = delivery.visibility is Visibility.EPHEMERAL
    viewer = delivery.to_identity if ephemeral else ""

    def send(_: Operation) -> CallOutcome:
        adapter.send(delivery.payload, to=delivery.chat_id, viewer=viewer, ephemeral=ephemeral)
        return CallOutcome.OK

    operation = send_operation(intent, channel=Channel.LARK, to=delivery.chat_id, viewer=viewer)
    return issue_once(ledger, operation, send)


# ------------------------------------------------------------ the wire (M10.2.1, M10.6.1)

#: Why an event is opened only after its signature is checked, and refused unless encrypted.
AN_EVENT_IS_SIGNED_ENCRYPTED_AND_TOKENED_OR_REFUSED: Final = (
    "A Lark event is refused unless its body is encrypted with the app's Encrypt Key, its "
    "signature over the time, the nonce and the exact bytes is the key's, the time is within five "
    "minutes, and the Verification Token inside it is the app's. The signature is checked before "
    "anything is decrypted. Lark's address check is the one request that may come unsigned: it is "
    "answered only when it decrypts under the key and carries the token, and it does nothing but "
    "echo its challenge."
)

#: Lark's headers for an event, lower-cased as `Arrived` holds them.
TIMESTAMP_HEADER: Final = "x-lark-request-timestamp"
NONCE_HEADER: Final = "x-lark-request-nonce"
SIGNATURE_HEADER: Final = "x-lark-signature"

#: The event this channel reads, and Lark's address check.
MESSAGE_RECEIVED: Final = "im.message.receive_v1"
URL_VERIFICATION: Final = "url_verification"

#: The tenant fields the Lark channel's record holds: the app, the platform it was made on, and
#: the bot's own open id, which is how a group message is known to be for it.
APP_ID_FIELD: Final = "app_id"
PLATFORM_FIELD: Final = "platform"
LARK_TENANT_FIELDS: Final = (APP_ID_FIELD, PLATFORM_FIELD, BOT_ID)

#: How far out of step Lark's timestamp may be. The window `brain.channels.webhook` uses, for
#: its reason: it bounds how long a captured signature is worth anything.
EVENT_WINDOW: Final = timedelta(minutes=5)

#: Lark's code for a call refused on rate, whatever the status beside it.
RATE_LIMITED_CODE: Final = 99991400

#: The largest card Lark accepts, and the ceiling a per-viewer body is held to.
MAX_CARD_BYTES: Final = 30 * 1024

#: How many people one page of a chat's members holds. Lark's documented maximum.
MEMBERS_PAGE: Final = 100

#: The three address kinds a reply is sent to, in the `to` string the ledger keys on.
ROOM_ADDRESS: Final = "chat"
SENDER_ADDRESS: Final = "user"
ASIDE_ADDRESS: Final = "aside"


def _refused() -> WebhookRefusedError:
    # One sentence for every reason, for `WebhookRefusedError`'s own: which check failed is
    # what somebody probing would fix next.
    return WebhookRefusedError("this request was not accepted")


@dataclass(frozen=True)
class LarkSecret:
    """The three values the Lark channel keeps in its one vault slot, and never the App ID.

    Kept as one compact JSON value because a channel has one slot (`providers/channel_lark`) and
    the vault's credential rule wants one unbroken line. The App ID is in the record's tenant,
    where the Channels screen may show it; nothing here is ever shown.
    """

    app_secret: str = field(repr=False)
    encrypt_key: str = field(repr=False)
    verification_token: str = field(repr=False)

    @classmethod
    def parse(cls, kept: str) -> LarkSecret:
        """The kept value read back, or `ValueError` for anything that is not all three."""
        try:
            parsed = json.loads(kept)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "the Lark channel's secret is not the value this module keeps"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise ValueError("the Lark channel's secret is not the value this module keeps")
        values = [parsed.get(name) for name in ("app_secret", "encrypt_key", "verification_token")]
        if not all(isinstance(one, str) and one for one in values):
            raise ValueError("the Lark channel's secret is missing one of its three values")
        app_secret, encrypt_key, token = (str(one) for one in values)
        return cls(app_secret=app_secret, encrypt_key=encrypt_key, verification_token=token)

    def kept(self) -> str:
        """The value written to the vault: compact, so it is one unbroken line."""
        return json.dumps(
            {
                "app_secret": self.app_secret,
                "encrypt_key": self.encrypt_key,
                "verification_token": self.verification_token,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def sign_event(encrypt_key: str, timestamp: str, nonce: str, body: bytes) -> str:
    """The signature Lark puts on an event: sha256 over the time, the nonce, the key and the
    bytes, as its server SDK computes it. Exported so a test signs with the one definition."""
    material = (timestamp + nonce + encrypt_key).encode("utf-8") + body
    return hashlib.sha256(material).hexdigest()


def open_event(encrypted: str, encrypt_key: str) -> bytes:
    """Lark's encrypted body, opened: AES-256-CBC under sha256 of the key, the IV first.

    Raises `WebhookRefusedError` for anything that does not open, including padding that is
    not PKCS#7, so a body encrypted under another key is a refusal and never a garbled read.
    """
    try:
        raw = base64.b64decode(encrypted, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _refused() from exc
    if len(raw) < 32 or len(raw) % 16:
        raise _refused()
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    decryptor = Cipher(algorithms.AES(key), modes.CBC(raw[:16])).decryptor()
    padded = decryptor.update(raw[16:]) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as exc:
        raise _refused() from exc


def _json_object(raw: bytes) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _refused() from exc
    if not isinstance(parsed, Mapping):
        raise _refused()
    return parsed


def _token_of(event: Mapping[str, Any]) -> str:
    """The Verification Token an opened event carries: in the header for schema 2.0 events and
    at the top for Lark's address check, as its SDK reads it."""
    header = event.get("header")
    found = header.get("token") if isinstance(header, Mapping) else event.get("token")
    return found if isinstance(found, str) else ""


def verify_event(
    *,
    secret: LarkSecret,
    body: bytes,
    timestamp: str,
    nonce: str,
    signature: str,
    now: datetime,
) -> bytes:
    """The event opened, or `WebhookRefusedError`. See the named constant for the order.

    Raises rather than returning a flag, for `brain.channels.webhook.verify`'s reason.
    """
    assert_raw_bytes(body)
    signed = bool(timestamp or nonce or signature)
    if signed:
        try:
            sent_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise _refused() from exc
        if abs(sent_at - now) > EVENT_WINDOW:
            raise _refused()
        expected = sign_event(secret.encrypt_key, timestamp, nonce, bytes(body))
        if not hmac.compare_digest(expected, signature):
            raise _refused()
    encrypted = _json_object(bytes(body)).get("encrypt")
    if not isinstance(encrypted, str) or not encrypted:
        raise _refused()
    opened = open_event(encrypted, secret.encrypt_key)
    event = _json_object(opened)
    if not hmac.compare_digest(_token_of(event), secret.verification_token):
        raise _refused()
    if not signed and event.get("type") != URL_VERIFICATION:
        # Only the address check may come unsigned; an event that should have been signed and
        # was not is the one a replay or a forgery would be.
        raise _refused()
    return opened


def _address(kind: str, *parts: str) -> str:
    return ":".join((kind, *parts))


def _host(tenant: Mapping[str, str]) -> str:
    platform = tenant.get(PLATFORM_FIELD, "")
    if platform not in LARK_PLATFORMS:
        msg = f"this channel's record names no Lark platform: one of {', '.join(LARK_PLATFORMS)}"
        raise ValueError(msg)
    return f"https://{LARK_PLATFORMS[platform][1]}"


def _exchange(host: str, tenant: Mapping[str, str], secret: LarkSecret) -> TokenExchange:
    app_id = tenant.get(APP_ID_FIELD, "")
    if not app_id:
        raise ValueError(f"this channel's record names no {APP_ID_FIELD}")
    body = json.dumps({"app_id": app_id, "app_secret": secret.app_secret}, separators=(",", ":"))
    return TokenExchange(
        url=f"{host}/open-apis/auth/v3/tenant_access_token/internal",
        body=body.encode("utf-8"),
        answered_in="tenant_access_token",
    )


def card_for(text: str) -> dict[str, Any]:
    """A per-viewer card carrying `text` as plain text: Lark's per-viewer message is a card.

    Plain text rather than Lark's markdown, so nothing in an answer is read as markup, and the
    label a payload carries survives into what is shown exactly as `render_body` wrote it.
    """
    return {
        "config": {"wide_screen_mode": True},
        "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": text}}],
    }


@dataclass(frozen=True)
class LarkWire:
    """`brain.channels.adapter.ChannelWire` for Lark. Holds no secret and opens nothing."""

    @property
    def channel(self) -> Channel:
        return Channel.LARK

    @property
    def tenant_fields(self) -> tuple[str, ...]:
        return LARK_TENANT_FIELDS

    def verify(self, arrived: Arrived, secret: str, now: datetime) -> Arrived:
        """`verify_event`, and the request back with its body opened."""
        try:
            kept = LarkSecret.parse(secret)
        except ValueError as exc:
            raise _refused() from exc
        opened = verify_event(
            secret=kept,
            body=arrived.body,
            timestamp=arrived.headers.get(TIMESTAMP_HEADER, ""),
            nonce=arrived.headers.get(NONCE_HEADER, ""),
            signature=arrived.headers.get(SIGNATURE_HEADER, ""),
            now=now,
        )
        return Arrived(headers=arrived.headers, body=opened)

    def handshake(self, arrived: Arrived) -> Mapping[str, str] | None:
        """Lark's address check, answered with its own challenge; None for an event."""
        event = _json_object(arrived.body)
        if event.get("type") != URL_VERIFICATION:
            return None
        challenge = event.get("challenge")
        if not isinstance(challenge, str) or not challenge:
            raise _refused()
        return {"challenge": challenge}

    def read(self, arrived: Arrived) -> Received:
        """A received message as the gate's event, and the three places a reply may go.

        Anything but `im.message.receive_v1` from a person is `ValueError`: no other event is
        subscribed to, and a message another app sent is not a question anybody asked.
        """
        try:
            event = _json_object(arrived.body)
        except WebhookRefusedError as exc:
            raise ValueError("an opened Lark event is a JSON object") from exc
        header = event.get("header")
        kind = header.get("event_type") if isinstance(header, Mapping) else None
        if kind != MESSAGE_RECEIVED:
            raise ValueError(f"this channel reads {MESSAGE_RECEIVED} and nothing else")
        body = event.get("event")
        sender = body.get("sender") if isinstance(body, Mapping) else None
        if not isinstance(sender, Mapping) or sender.get("sender_type") != "user":
            raise ValueError("a message another app sent is not a question anybody asked")
        try:
            message = normalise_message(event)
        except LarkRefusedError as exc:
            raise ValueError(str(exc)) from exc
        sender_id = message.event.channel_identity
        room = _address(ROOM_ADDRESS, message.chat_id)
        shared = not audience_is_one_person(message.chat_type)
        return Received(
            event=message.event,
            reply_to=room,
            conversation=Conversation(
                room_to=room,
                sender_to=_address(SENDER_ADDRESS, sender_id),
                conversation_id=message.chat_id,
                shared=shared,
                aside_to=_address(ASIDE_ADDRESS, message.chat_id, sender_id) if shared else "",
                addressed=frozenset(one.identity for one in message.mentions),
            ),
        )

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        """The send for one address, with the token exchange that authorises it beside it.

        `chat:` posts to a conversation, `user:` sends to one person's own chat with the bot, and
        `aside:` sends a card only that person sees inside a group. `ValueError` for an address
        of no kind, a record short of what Lark needs, or a card larger than Lark takes.
        """
        del now  # Lark stamps its own time; the parameter is the protocol's.
        kept = LarkSecret.parse(secret)
        host = _host(tenant)
        kind, _, rest = to.partition(":")
        if kind in (ROOM_ADDRESS, SENDER_ADDRESS) and rest:
            id_type = "chat_id" if kind == ROOM_ADDRESS else "open_id"
            url = f"{host}/open-apis/im/v1/messages?{urlencode({'receive_id_type': id_type})}"
            payload: dict[str, Any] = {
                "receive_id": rest,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            }
        elif kind == ASIDE_ADDRESS and rest.count(":") == 1:
            chat_id, open_id = rest.split(":")
            url = f"{host}/open-apis/ephemeral/v1/send"
            payload = {
                "chat_id": chat_id,
                "open_id": open_id,
                "msg_type": "interactive",
                "card": card_for(text),
            }
            if len(json.dumps(payload["card"]).encode("utf-8")) > MAX_CARD_BYTES:
                raise ValueError("this answer is larger than a Lark card takes")
        else:
            raise ValueError(f"{to!r} is not an address this channel sends to")
        return VendorRequest(
            url=url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            exchange=_exchange(host, tenant, kept),
        )

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        """Lark's `code` decides, because Lark refuses inside a 200.

        Zero with a 200 is delivered; the rate code is a quota at any status; any other code is
        a refusal. A 200 whose body cannot be read may have been delivered, so it is not known
        rather than sent. Everything with no body to read is `classify`'s.
        """
        if answer.unsafe_address:
            return CallOutcome.REJECTED
        code = _code(answer.body)
        if code == RATE_LIMITED_CODE:
            return CallOutcome.QUOTA
        if answer.status == 200:
            if code is None:
                return CallOutcome.UNAVAILABLE
            return CallOutcome.OK if code == 0 else CallOutcome.REJECTED
        outcome = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed,
        )
        return CallOutcome.REJECTED if outcome is CallOutcome.OK else outcome

    def members_request(
        self, *, conversation_id: str, page: str, secret: str, tenant: Mapping[str, str]
    ) -> VendorRequest:
        """One page of who is in a chat, by open id. The read a group's floor needs (M10.4.1).

        Lark leaves the chat's bots out of this list, the bot included, so the list is people.
        """
        kept = LarkSecret.parse(secret)
        host = _host(tenant)
        query = {"member_id_type": "open_id", "page_size": str(MEMBERS_PAGE)}
        if page:
            query["page_token"] = page
        return VendorRequest(
            url=(
                f"{host}/open-apis/im/v1/chats/{quote(conversation_id, safe='')}/members"
                f"?{urlencode(query)}"
            ),
            headers={},
            body=b"",
            method="GET",
            exchange=_exchange(host, tenant, kept),
        )

    def members_page(self, answer: VendorAnswer) -> tuple[frozenset[str], str]:
        """The digests of the people on one page, and the next page's token or empty.

        Digested at once, so no open id outlives this call. `ValueError` for any answer that is
        not a page: a floor computed over a list that failed to read would be a floor over nobody.
        """
        if self.judge(answer) is not CallOutcome.OK:
            raise ValueError("Lark did not answer with who is in this chat")
        data = _json_object(answer.body).get("data")
        if not isinstance(data, Mapping):
            raise ValueError("Lark's page of members has no data")
        items = data.get("items") or []
        if not isinstance(items, list):
            raise ValueError("Lark's page of members is not a list")
        found = set()
        for item in items:
            member = item.get("member_id") if isinstance(item, Mapping) else None
            if not isinstance(member, str) or not member:
                raise ValueError("a member on Lark's page has no id")
            found.add(identity_hash(Channel.LARK, member))
        more = data.get("has_more") is True
        token = data.get("page_token")
        return frozenset(found), (token if more and isinstance(token, str) else "")


def _code(body: bytes) -> int | None:
    """Lark's `code` from an answer's body, or None when there is no readable one."""
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    code = parsed.get("code") if isinstance(parsed, Mapping) else None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


#: This channel's wire, found by `brain.channels.adapter.channel_wires`.
WIRE: Final = LarkWire()
