"""What every channel adapter must do, and the two things it may not.

An adapter is a translator: what arrived becomes a `ChannelEvent`, and a `ChannelPayload`
becomes whatever the surface renders. It decides nothing about who may see what, because
the gate already did - and a channel that could decide again would be a second opinion,
with the permissive one winning the day the two disagree.

Two refusals are built into the shape rather than left to each adapter to remember.

**An adapter that cannot render the payload's label must refuse to send (M10.1.5).** The
opaque escape hatch exists so a tool that returns something the redactor cannot walk is not
simply unusable; the price is a label saying so, carried all the way to the person. An
adapter that dropped the label - because SMS has no formatting, because a card template had
nowhere to put it - would turn "here is something nobody checked" into "here is an answer",
which is the one transformation the escape hatch must never undergo. So `send` is written to
refuse rather than to degrade, and `can_carry_label` is what an adapter answers with.

**An adapter may not carry a classification above its ceiling (M10.1.3).** WhatsApp is a
consumer messaging app on somebody's personal phone; the console is behind the identity
provider. Those are not the same surface and a field classified `restricted` should not be
in the first one because the answer happened to be asked for there. The ceiling is per
channel and it is checked here rather than trusted to whoever writes the next adapter.

**The channels are found, not listed (M10.1.1).** `channel_adapters` reads every module under
`brain.channels` for a class shaped like `ChannelAdapter`, and `channel_wires` for a module-level
`WIRE`. A channel package adds its file and nothing else: no list in `brain.agent_routes`, no
import in the receiving route. See `A_CHANNEL_IS_ADDED_BY_ADDING_ITS_FILE`.

**A wire is the part of a channel that meets the vendor, and it holds no client.** `ChannelWire`
verifies what arrived over the exact bytes, reads it into a `ChannelEvent`, and builds the
request that would deliver a reply; `ChannelTransport` is the one thing that puts a request on the
network. The split is the adapter's own argument carried one step further: every decision a wire
makes is a function of bytes and a secret, so it is tested without a vendor, and the transport is
one class for every channel rather than one HTTP client per adapter. The secret is a parameter and
never a field, because a wire outlives every request and a key it held would too.

Rejected: a wire method that posts. It would put a socket in every channel module, which
`tests/invariants/test_channel_adapter_invariants.py` refuses for the adapters for the reason it
gives, and every wire would then need its own address check against the rule
`brain.tools.fetch.assert_fetchable` holds once.

**A chat's wire says where a message was said, and a vendor's credential can be exchanged for its
token on the way out.** `Received.conversation` carries the three addresses a reply can go to, who
reads each, and who the message named, so the decision about who reads an answer is made over
shapes rather than over one vendor's strings. `VendorRequest.exchange` carries the exchange a
vendor like Lark asks before every request, and `verify` hands back the request opened, for a
vendor that encrypts. All three arrived with the Lark channel and change nothing for a wire that
declares none of them.

**A channel's connect steps sit beside its wire, and hold its own form once.** A module with a
`WIRE` may declare `GUIDE`, the `brain.ops.connect_steps.GuideStep` screens that walk a person
through the vendor, and `channel_guides` finds them as `channel_wires` finds the wires. One step
asks for exactly the wire's tenant fields and its secret, or the secret's parts, which is what the
channel's record takes, so a flow cannot hold a form that saves something else. See
`A_CHANNEL_S_STEPS_HOLD_ITS_OWN_FORM_ONCE`.

Task ids: M10.1.1, M10.1.2, M10.1.3, M10.1.4, M10.1.5, M10.2.1, M10.6.1, M10.2.6, M10.5.6
"""

from __future__ import annotations

import enum
import functools
import importlib
import pkgutil
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from brain.connectors.throttle import CallOutcome
from brain.core.field_policy import Classification
from brain.core.redaction import OPAQUE_LABEL, ChannelPayload
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent
from brain.ops.connect_steps import GuideStep
from brain.ops.idempotency import Intent, Operation, operation_for

if TYPE_CHECKING:
    from brain.identity.oidc import KeySet


class DeliveryRefusedError(Exception):
    """Raised when a payload must not go out over this channel.

    Not a `BrainError`, because it is not an outcome of a request: it is a wiring fault or a
    policy boundary, and reporting it as `Degraded` would put "this channel cannot carry
    this" in the same bucket as "the provider is down".
    """


class Feature(enum.StrEnum):
    """What a surface can actually do. Closed, because each member gates a code path.

    Declared per adapter rather than inferred. Inferring means guessing, and a wrong guess
    about `EPHEMERAL` is the one that matters: a per-viewer body sent to a channel that
    cannot do ephemeral messages is a private answer posted into a room.
    """

    #: Messages only that person sees, in a shared room. The mechanism M10.4.2 needs.
    EPHEMERAL = "ephemeral"
    #: Structured, actionable messages. Approvals need these or they degrade to a link.
    CARDS = "cards"
    #: Tokens as they arrive rather than one finished message.
    STREAMING = "streaming"
    #: Files out, and files in.
    ATTACHMENTS = "attachments"
    #: Editing a message already sent, which is how a card stops being actionable once the
    #: approval it offers has been taken by somebody else.
    EDIT_IN_PLACE = "edit_in_place"
    #: The agent can be installed into a shared conversation rather than only into a
    #: one-to-one one. Added for M39.2.4.4 and honoured by
    #: `brain.console.agent_tabs.install_to_group`, which refuses an install on a surface
    #: that does not declare it, so this is a member with a code path behind it rather than
    #: a label an adapter can wear. **No adapter in this repository declares it yet**, and
    #: that is the honest state: a group install needs a path for the conversation reference
    #: the vendor hands back, and none of the six adapters has one. Declaring it is a
    #: decision per surface, made where the surface's other capabilities are argued.
    GROUP_INSTALL = "group_install"


@dataclass(frozen=True)
class ChannelCapabilities:
    """What one adapter can do and how sensitive a thing it may carry (M10.1.2, M10.1.3).

    Frozen, and read at send time rather than at registration, so an adapter cannot widen
    itself between the check and the send.
    """

    channel: Channel
    features: frozenset[Feature] = frozenset()
    #: The most sensitive classification this surface may carry. Not a list of allowed
    #: classes: sensitivity is ordered, and a list would let somebody permit `restricted`
    #: while forbidding `confidential`, which is a configuration nobody means and which
    #: reads as deliberate.
    max_classification: Classification = Classification.INTERNAL
    #: Whether a label can be rendered where a person will see it. An adapter answering
    #: false here can still be used for anything unlabelled; it simply cannot carry the
    #: opaque escape hatch. See `assert_can_send`.
    can_carry_label: bool = True

    def supports(self, feature: Feature) -> bool:
        return feature in self.features

    def may_carry(self, classification: Classification) -> bool:
        return classification.rank <= self.max_classification.rank


@runtime_checkable
class ChannelAdapter(Protocol):
    """One surface. Three methods and no fourth.

    There is deliberately no `query`, no `fetch` and no `check`. An adapter that could ask
    the database a question would be a second path to data with its own idea of what may be
    seen; everything it sends comes from a `ChannelPayload` the gate produced.
    """

    def capabilities(self) -> ChannelCapabilities: ...

    def normalise(self, raw: object) -> ChannelEvent:
        """Whatever arrived, as the one shape the gate reads."""
        ...

    def send(self, payload: ChannelPayload, *, to: str, body: str = "") -> None:
        """Deliver. Must call `assert_can_send` first, or inherit a base that does.

        `body` empty means render the payload; a body given is what a person reads, and the
        adapter checks the payload's label survived into it. Part of the protocol since
        M34.2.2.1, because `brain.channels.correction` puts the line that lets a person say
        an answer was wrong into the body, and an adapter whose send could not carry a
        composed body was an adapter nobody could correct an answer from.
        """
        ...

    def healthy(self, now: datetime) -> bool:
        """Whether this adapter can currently deliver (M10.1.4).

        Separate from whether it is *registered*. An adapter that is configured and
        unreachable must read as unhealthy rather than as absent: absent means nobody set it
        up, and the two send a person to different places.
        """
        ...


def assert_can_send(
    capabilities: ChannelCapabilities,
    payload: ChannelPayload,
    *,
    highest: Classification = Classification.INTERNAL,
) -> None:
    """The two refusals every adapter shares, in one place so no adapter can forget one.

    Called by `send`, not by the caller of `send`. A check the caller performs is a check
    that is missing from the one call site somebody adds later, and the point of putting it
    here is that an adapter has to go out of its way to skip it.

    `highest` is the most sensitive classification in what is being sent. It is passed in
    rather than computed from the payload, because a `ChannelPayload` carries values and not
    the policy that classified them - by design, since a payload that knew its own
    classification would be carrying the policy to the channel.
    """
    if payload.label == OPAQUE_LABEL and not capabilities.can_carry_label:
        raise DeliveryRefusedError(
            f"{capabilities.channel} cannot render a payload label, and this payload carries "
            f"{OPAQUE_LABEL!r}. Sending it without the label turns 'here is something nobody "
            "checked' into 'here is an answer', which is the one thing the opaque escape "
            "hatch must never become."
        )

    if not capabilities.may_carry(highest):
        # The message names the channel and the classification and not the field or the
        # value: a refusal that quoted either would put the sensitive thing into whatever
        # log records the refusal.
        raise DeliveryRefusedError(
            f"{capabilities.channel} may carry at most {capabilities.max_classification} "
            f"and this answer contains {highest}"
        )


def registered(adapters: dict[Channel, ChannelAdapter], now: datetime) -> dict[Channel, bool]:
    """Every registered adapter and whether it can currently deliver (M10.1.4).

    Returns a mapping rather than a list of the healthy ones, because "not registered" and
    "registered and unhealthy" are different problems that send a person to different
    places, and a filtered list makes them look identical.

    An adapter whose health check raises is unhealthy rather than an error out of this
    function. A single broken adapter must not make the health of every other one
    unanswerable, which is what an exception escaping here would do.
    """
    out: dict[Channel, bool] = {}
    for channel, adapter in adapters.items():
        try:
            out[channel] = adapter.healthy(now)
        except Exception:
            out[channel] = False
    return out


def send_operation(intent: Intent, *, channel: Channel, to: str, viewer: str = "") -> Operation:
    """The operation one message to one destination on one channel is (M17.3.1).

    Every `deliver` in this package sends through `brain.ops.idempotency.issue_once` under this,
    so a delivery retried, resumed or raced by a second worker posts once. The destination and
    the viewer are arguments, because the same answer to two chats, or to two people in one, is
    two messages; the body is not, because a retried turn may word its answer differently and is
    still the same answer. Who is acting and which turn asked are the caller's, handed in as the
    intent, for `brain.ops.idempotency.A_KEY_IS_DERIVED_NEVER_GENERATED`'s reason.
    """
    return operation_for(
        intent,
        connector=channel.value,
        tool=f"{channel.value}.send",
        arguments={"to": to, "viewer": viewer},
    )


# --------------------------------------------------------------- the registry (M10.1.1)

#: Why the adapters and the wires are discovered rather than listed.
A_CHANNEL_IS_ADDED_BY_ADDING_ITS_FILE: Final = (
    "The adapters and the wires are found by reading brain.channels, so a channel package adds "
    "its module and nothing else. A list kept by hand elsewhere is the one that misses the next "
    "surface, and a surface it misses is offered nowhere and received on nowhere with every test "
    "of it green."
)

#: The name a channel module gives its wire, so discovery reads one attribute and guesses nothing.
WIRE_NAME: Final = "WIRE"

#: The module attribute a channel's connect steps are declared under, beside its `WIRE`.
GUIDE_NAME: Final = "GUIDE"

#: What a channel's form step asks for besides its record's fields: its one secret.
SECRET_ASK: Final = "secret"  # noqa: S105  a field name, not a secret

#: The ask a step names to show this install's events address, which it shows and never collects.
EVENTS_ADDRESS_ASK: Final = "events_address"

#: Why a secret of several parts is written as a whole.
SEVERAL_PARTS_ARE_WRITTEN_AS_ONE: Final = (
    "A channel whose vendor needs more than one secret keeps them together in its one vault "
    "slot, written as a whole: every part is given at once or none is, so a record never holds "
    "one part new and another from before, and the route never reads a secret back to merge it."
)

#: Why a channel's steps hold its record's form once, and ask for nothing else.
A_CHANNEL_S_STEPS_HOLD_ITS_OWN_FORM_ONCE: Final = (
    "A channel's connect steps hold one screen that saves its record, asking for the fields its "
    "wire takes and its secret, so a field the wire gains is a field the steps ask for too; every "
    "other screen asks for nothing but to be shown the events address. Where the steps branch, "
    "each path holds one such form, asking the fields that path needs, and every field is asked "
    "on some path. The form need not be last: a vendor that checks the address as it is saved is "
    "told to check it after."
)

#: The adapter methods a class needs to be read as an adapter. `ChannelAdapter`'s, by name.
_ADAPTER_METHODS: Final = ("capabilities", "normalise", "send", "healthy")


class ChannelRegistryError(Exception):
    """Two adapters or two wires claim one channel, or a wire has no adapter to declare it.

    Raised at discovery rather than resolved, because either answer is a guess about which
    declaration of a surface's ceiling is the real one.
    """


def _channel_modules() -> Iterator[ModuleType]:
    """Every module in `brain.channels`, in name order, imported."""
    import brain.channels

    for info in sorted(pkgutil.iter_modules(brain.channels.__path__), key=lambda one: one.name):
        yield importlib.import_module(f"brain.channels.{info.name}")


def _is_adapter_class(candidate: object, module: ModuleType) -> bool:
    """A class this module defines, not a protocol, answering every `ChannelAdapter` method.

    The same test `tests/invariants/test_redaction_invariants.py` discovers adapters by, so the
    registry and the invariant that checks every adapter cannot disagree about which exist.
    """
    return (
        isinstance(candidate, type)
        and candidate.__module__ == module.__name__
        and not getattr(candidate, "_is_protocol", False)
        and all(callable(getattr(candidate, name, None)) for name in _ADAPTER_METHODS)
    )


@functools.cache
def channel_adapters() -> tuple[Callable[[], ChannelAdapter], ...]:
    """Every adapter this product ships, one per channel, in channel order (M10.1.1).

    Each is constructed once, bare, to ask which channel it declares. None of them takes an
    argument or holds a credential, for the reason `brain.agent_routes.CHANNEL_ADAPTERS` gives,
    so asking opens nothing and reads no configuration.
    """
    found: dict[Channel, Callable[[], ChannelAdapter]] = {}
    for module in _channel_modules():
        for candidate in vars(module).values():
            if not _is_adapter_class(candidate, module):
                continue
            factory: Callable[[], ChannelAdapter] = candidate
            channel = factory().capabilities().channel
            if channel in found:
                msg = f"two adapters declare {channel}; {A_CHANNEL_IS_ADDED_BY_ADDING_ITS_FILE}"
                raise ChannelRegistryError(msg)
            found[channel] = factory
    return tuple(found[channel] for channel in sorted(found))


def adapter_for(channel: Channel) -> ChannelAdapter:
    """A fresh adapter for this channel. Raises `KeyError` for a channel no adapter declares."""
    for factory in channel_adapters():
        adapter = factory()
        if adapter.capabilities().channel is channel:
            return adapter
    raise KeyError(channel.value)


@functools.cache
def channel_wires() -> Mapping[Channel, ChannelWire]:
    """Every channel that can receive and reply, by channel. See `ChannelWire`.

    A wire whose channel no adapter declares is refused: sending checks the adapter's declared
    ceiling and label, and a wire with nothing declaring them would send past both.
    """
    declared = {factory().capabilities().channel for factory in channel_adapters()}
    found: dict[Channel, ChannelWire] = {}
    for module in _channel_modules():
        wire = getattr(module, WIRE_NAME, None)
        if wire is None:
            continue
        channel = wire.channel
        if found.get(channel) is wire:
            # The same wire imported into a second module is one wire, not two.
            continue
        if channel in found:
            msg = f"two wires claim {channel}; {A_CHANNEL_IS_ADDED_BY_ADDING_ITS_FILE}"
            raise ChannelRegistryError(msg)
        if channel not in declared:
            msg = f"{channel} has a wire and no adapter to declare what it may carry"
            raise ChannelRegistryError(msg)
        found[channel] = wire
    return MappingProxyType(found)


def guide_problem(steps: tuple[GuideStep, ...], wire: ChannelWire) -> str:
    """What is wrong with a channel's steps, or empty; see the rule it names.

    `A_CHANNEL_S_STEPS_HOLD_ITS_OWN_FORM_ONCE` is the rule.

    With no choice among them, the one form asks every field the record takes. With a choice,
    each path, the steps on no path and the steps on it, holds one form asking some of the fields,
    and the paths' forms together ask every field.
    """
    secret = tuple(wire.secret_parts or (SECRET_ASK,))
    fields = set(wire.tenant_fields)
    paths = [key for one in steps for key, _ in one.choices]
    unknown = sorted({one.path for one in steps if one.path} - set(paths))
    if unknown:
        return f"name paths no step offers: {unknown}"

    def is_form(step: GuideStep) -> bool:
        asked = tuple(step.asks)
        leading = asked[: len(asked) - len(secret)]
        return asked[len(asked) - len(secret) :] == secret and set(leading) <= fields

    asked_somewhere: set[str] = set()
    for path in paths or [""]:
        seen = [one for one in steps if one.path in ("", path)]
        forms = [one for one in seen if is_form(one)]
        stray = sorted(
            {ask for one in seen if not is_form(one) for ask in one.asks} - {EVENTS_ADDRESS_ASK}
        )
        if len(forms) != 1 or stray:
            where = f"on path {path!r} " if path else ""
            return f"{where}hold {len(forms)} form(s) and ask for {stray}"
        asked_somewhere |= set(forms[0].asks[: len(forms[0].asks) - len(secret)])
    if asked_somewhere != fields:
        return f"ask {sorted(asked_somewhere)} of the record's {sorted(fields)}"
    return ""


def channel_guides() -> Mapping[Channel, tuple[GuideStep, ...]]:
    """Every channel's connect steps, by channel: a module's `GUIDE`, beside its `WIRE`.

    A guide in a module with no wire is refused, since there is nothing its form could save, and
    so is one without exactly one step asking for the wire's fields and its secret, or with a step
    asking for anything else. See `A_CHANNEL_S_STEPS_HOLD_ITS_OWN_FORM_ONCE`.
    """
    wires = channel_wires()
    found: dict[Channel, tuple[GuideStep, ...]] = {}
    for module in _channel_modules():
        guide = getattr(module, GUIDE_NAME, None)
        if guide is None:
            continue
        declared: object = getattr(module, WIRE_NAME, None)
        wire = next((one for one in wires.values() if one is declared), None)
        if wire is None:
            msg = f"{module.__name__} declares connect steps and no wire they could set up"
            raise ChannelRegistryError(msg)
        steps = tuple(guide)
        problem = guide_problem(steps, wire)
        if problem:
            msg = f"{wire.channel}'s steps {problem}. {A_CHANNEL_S_STEPS_HOLD_ITS_OWN_FORM_ONCE}"
            raise ChannelRegistryError(msg)
        found[wire.channel] = steps
    return MappingProxyType(found)


# ------------------------------------------------------------- the wire (M10.2.1, M10.6.1)


@dataclass(frozen=True)
class Arrived:
    """A request as it arrived: its headers, names lower-cased, and its body's exact bytes.

    Bytes and never a parsed body, for `brain.channels.webhook`'s first argument: a signature
    covers what was sent, and a re-serialisation is something the sender never signed.

    `tenant` and `keys` are what a vendor that signs with a published key needs besides the
    secret: the record's identifiers, which such a token names, and the keys the vendor
    publishes, fetched by the route for a `KeyedWire` and absent for every other. See
    `A_PUBLISHED_KEY_IS_FETCHED_BY_THE_ROUTE_AND_JUDGED_BY_THE_WIRE`.
    """

    headers: Mapping[str, str]
    body: bytes = field(repr=False)
    #: The record's identifiers, for a wire whose check depends on how the record is set up.
    tenant: Mapping[str, str] = field(default_factory=dict)
    keys: KeySet | None = None


@dataclass(frozen=True)
class Conversation:
    """Where a chat message was said, for a channel whose conversations can hold more than one.

    Three addresses because a reply has three possible audiences, and choosing among them is a
    permission decision rather than a formatting one: `room_to` is read by everybody in the
    conversation, `sender_to` by the sender alone in a conversation of their own with the bot,
    and `aside_to` by the sender alone inside this one, the vendor's per-viewer message, or empty
    where the vendor has none. `addressed` holds the digests of the identities the message named,
    keyed on the vendor's own ids, so a shared conversation is answered only when it named the
    bot (M10.2.2, M10.2.6); see `BOT_ID`.
    """

    room_to: str
    sender_to: str
    #: The vendor's own id for the conversation, for reading who is in it.
    conversation_id: str
    #: More than one person reads what is posted to `room_to`.
    shared: bool
    aside_to: str = ""
    addressed: frozenset[str] = frozenset()


#: The tenant field a channel with shared conversations names its own bot in: the vendor's id for
#: it. A message in a shared conversation that does not name that identity is not for the bot.
BOT_ID: Final = "bot_id"


@dataclass(frozen=True)
class Received:
    """A verified request, read: the event the gate reads and where a reply to it goes."""

    event: ChannelEvent
    #: The vendor's address for a reply: a chat, a conversation, a sender. Never a principal.
    reply_to: str
    #: Present for a chat whose conversations can hold more than one reader. None for a channel
    #: where the reply goes back to the sender alone, as the company's own system's does.
    conversation: Conversation | None = None


@dataclass(frozen=True)
class VendorRequest:
    """One request to a vendor, built and not sent. The headers may carry the credential.

    `repr=False` on the headers and the body, because this object is built with the secret in
    hand and the commonest way a key reaches a log is an exception handler formatting the object
    it was holding; see `brain.ops.secrets.Lease`.
    """

    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    #: `POST` to deliver; `GET` for the one read a chat needs, who is in a conversation.
    method: str = "POST"
    #: A credential exchanged for a bearer token first, for a vendor that authorises requests
    #: with a token of its own minting rather than with the secret itself.
    exchange: TokenExchange | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TokenExchange:
    """A POST that exchanges the channel's credential for a short-lived bearer token.

    Carried on the request rather than made by the wire, because a wire opens no connection. The
    transport makes it immediately before the request it authorises and keeps the token nowhere,
    so a token is never older than one delivery and never outlives it. `answered_in` names where
    in the vendor's JSON answer the token is. `repr=False` for `VendorRequest`'s reason: the body
    holds the credential.
    """

    url: str
    body: bytes = field(repr=False)
    answered_in: str = "access_token"  # the JSON key, not a value
    #: How the body is written: JSON for most vendors, a form for an OAuth token endpoint.
    content_type: str = "application/json; charset=utf-8"


@dataclass(frozen=True)
class VendorAnswer:
    """What one request did at the vendor, in the terms `brain.connectors.throttle.classify` reads.

    `unsafe_address` is this side refusing to connect, because the vendor's address resolved
    somewhere only this network can reach; nothing was sent. `body` is what the vendor answered
    with, for a wire whose vendor says 200 and refuses in the body, and for the one read a chat
    makes; `brain.channel_routes.HttpsTransport` keeps it up to its bound.
    """

    status: int | None = None
    timed_out: bool = False
    connection_failed: bool = False
    unsafe_address: bool = False
    body: bytes = field(default=b"", repr=False)


class ChannelWire(Protocol):
    """How one channel meets its vendor, as functions of bytes and a secret. No client.

    Found as the module attribute `WIRE` in a `brain.channels` module; see `channel_wires`. Every
    method is pure: none opens a connection or reads the vault, so the route decides when the
    body is read and when the secret is borrowed, and a wire cannot decide either for it.
    """

    @property
    def channel(self) -> Channel:
        """The channel this wire receives and replies on."""
        ...

    @property
    def tenant_fields(self) -> tuple[str, ...]:
        """The tenant identifiers a record for this channel must hold, by name."""
        ...

    @property
    def secret_parts(self) -> tuple[str, ...]:
        """The named values this channel's secret holds, or empty when it is one value.

        A vendor that signs what it sends with one secret and takes its replies on another has
        two, and both belong in the vault: the route keeps them together, as one JSON object in
        the channel's one slot, and `verify` and `request_for` each read the part they need. See
        `SEVERAL_PARTS_ARE_WRITTEN_AS_ONE`.
        """
        ...

    def verify(self, arrived: Arrived, secret: str, now: datetime) -> Arrived:
        """Refuse, with `brain.channels.webhook.WebhookRefusedError`, anything the vendor did not
        send. Over the exact bytes, and before `read` looks at any of them.

        Returns the request as `handshake` and `read` are to see it: the same request, or, for a
        vendor that encrypts what it sends, the request with its body opened. Opening belongs to
        verifying because its key is the secret, and only this method is handed the secret."""
        ...

    def handshake(self, arrived: Arrived) -> Mapping[str, str] | None:
        """A verified request that is the vendor checking the address, answered with this body,
        or None for a message. Such a request is answered and never claimed."""
        ...

    def read(self, arrived: Arrived) -> Received:
        """The verified request as an event and its reply address, or `ValueError`."""
        ...

    def request_for(
        self, *, to: str, text: str, secret: str, tenant: Mapping[str, str], now: datetime
    ) -> VendorRequest:
        """The request that delivers `text` to `to`, or `ValueError` when the tenant lacks
        what the vendor needs. `text` is rendered already, with any label in it."""
        ...

    def judge(self, answer: VendorAnswer) -> CallOutcome:
        """What the vendor's answer says about the delivery. A vendor that answers 200 with a
        refusal in its body is judged here, by the wire that knows that vendor."""
        ...


#: Why a vendor's published keys are fetched outside the wire and read inside it.
A_PUBLISHED_KEY_IS_FETCHED_BY_THE_ROUTE_AND_JUDGED_BY_THE_WIRE: Final = (
    "A vendor that signs with a key it publishes, rather than with a secret shared with the "
    "install, needs those keys to verify anything. The route fetches them from the one address "
    "the wire names and caches them for every request; the wire, which opens no connection, "
    "judges the token against them, and refuses whatever arrives when none could be fetched."
)


@runtime_checkable
class KeyedWire(Protocol):
    """A wire whose vendor signs with published keys: where they are, and how to read them.

    `keys_address` is the vendor's OpenID metadata document. `key_set_of` reads that document
    and the key set it points to into the keys `verify` is handed on `Arrived.keys`; the route
    fetches both, and only from an address this names or the document gives on the same host.
    """

    @property
    def keys_address(self) -> str: ...

    def key_set_of(self, metadata: bytes, keys: bytes, now: datetime) -> KeySet: ...


class ChannelTransport(Protocol):
    """Whatever puts a `VendorRequest` on the network. `brain.channel_routes.HttpsTransport`.

    Synchronous, for `brain.ops.outbox_store.Sender`'s reason: it is called inside the effect
    `issue_once` runs. It never raises for anything the network did; a silence is `timed_out`.

    `read` is the other half, and a separate method so the two cannot be confused: a `GET` that
    changes nothing at the vendor, the one read a chat makes, who is in a conversation. It refuses
    anything but a `GET`, so a send cannot reach the vendor by the door that is not keyed.
    """

    def send(self, request: VendorRequest) -> VendorAnswer: ...

    def read(self, request: VendorRequest) -> VendorAnswer: ...
