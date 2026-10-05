"""Where the evening digest goes: one install setting naming a connected channel and a
conversation in it, chosen from what each channel offers and never typed.

The owner decided this in `docs/needs-rupash.md` item 125: the digest is not tied to Lark. It is
one setting, **Send the evening digest to**, that offers every channel connected at the time and
a conversation in it, is off until somebody chooses, and records who changed it. Every install
chooses its own in the same place, so nothing here names a company, a group or an id.

**The setting holds `channel:conversation`, and a person never types it.** `offered` asks each
connected channel for the conversations it can post to, and the route that saves a choice
(`brain.digest_routes`) refuses anything that is not on that list at the moment of saving. An id
somebody typed is the one that is wrong by a character and posts nowhere, or posts into a chat
the person did not mean, and a digest names every open task of the build.

**A channel offers conversations only if its wire can list them.** `ConversationLister` is the
optional half of `brain.channels.adapter.ChannelWire` a wire implements for this: Lark lists the
groups its bot has been added to (`brain.channels.lark.LarkWire.conversations_request`). A channel
that cannot list, or is not connected, offers nothing and is not a choice, which is the honest
answer: a channel connected later offers its own conversations the day it is connected, with no
change here.

**Connected is three facts, read the way the send path reads them.** A record for the channel,
switched on, and its secret held in the vault. `standing` answers whether the saved destination
still meets all three, and the words say which one it does not, so the Settings row can tell a
person why the digest has stopped rather than just that it has.

Rejected: a free-text field with a validation pattern. It would accept a well-formed id for a
chat the bot is not in, which fails at six in the evening instead of at the moment of choosing.

Task ids: M38.3.3.1, M38.3.3.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from brain.channels.adapter import ChannelTransport, VendorAnswer, VendorRequest, channel_wires
from brain.gate.context import Channel
from brain.ops.channel_store import (
    ChannelRecord,
    ChannelSecrets,
    ChannelSecretsUnavailableError,
)

# ------------------------------------------------------------------ written-down reasons
#: Why the destination is chosen from a list.
A_DESTINATION_IS_CHOSEN_FROM_WHAT_THE_CHANNEL_OFFERS: Final = (
    "The evening digest names every open task of the build, so where it goes is chosen from the "
    "conversations a connected channel says it can post to, and a choice that is not on that list "
    "at the moment of saving is refused. A typed id is the one that is wrong by a character."
)

# ------------------------------------------------------------------------ the setting
#: The install setting holding the destination, `channel:conversation` or `unset`.
DESTINATION_SETTING: Final = "INSTALL_DIGEST_DESTINATION"

#: The install setting holding the time of day the digest is sent, `HH:MM` in the install's zone.
SEND_TIME_SETTING: Final = "INSTALL_DIGEST_TIME"

#: What the setting holds when nobody has chosen, which sends nothing.
UNSET: Final = "unset"

#: The separator between the channel and the conversation in the saved value.
SEPARATOR: Final = ":"

#: How many pages of one channel's conversations are read before the list is called long enough.
MAX_PAGES: Final = 10


@dataclass(frozen=True)
class Destination:
    """A channel and one of its conversations."""

    channel: Channel
    conversation: str

    def __post_init__(self) -> None:
        if not self.conversation.strip() or SEPARATOR in self.channel.value:
            msg = "a destination names a channel and a conversation in it"
            raise ValueError(msg)

    @property
    def saved(self) -> str:
        """As the setting holds it."""
        return f"{self.channel.value}{SEPARATOR}{self.conversation}"


def destination_of(saved: str) -> Destination | None:
    """The destination a saved value names, or None when it is unset or unreadable.

    Unreadable reads as unset rather than raising: the setting is the digest's switch, and a value
    nobody can read is a digest that sends nothing, which `standing` then says.
    """
    written = saved.strip()
    if not written or written == UNSET or SEPARATOR not in written:
        return None
    channel, _, conversation = written.partition(SEPARATOR)
    try:
        return Destination(Channel(channel), conversation)
    except ValueError:
        return None


# ------------------------------------------------------------------------ what is offered
@runtime_checkable
class ConversationLister(Protocol):
    """A wire that can list the conversations it may post to. `brain.channels.lark.LarkWire`."""

    def conversations_request(
        self, *, page: str, secret: str, tenant: Mapping[str, str]
    ) -> VendorRequest: ...

    def conversations_page(
        self, answer: VendorAnswer
    ) -> tuple[tuple[tuple[str, str], ...], str]: ...


@dataclass(frozen=True)
class Offered:
    """One conversation a channel offers, as a person chooses it."""

    destination: Destination
    name: str


@dataclass(frozen=True)
class ChannelOffer:
    """What one connected channel offers, or why it offers nothing."""

    channel: Channel
    conversations: tuple[Offered, ...]
    #: Empty when the list was read; otherwise the one sentence saying why it was not.
    why_none: str = ""


#: Said for a channel with no record, switched off, or with no secret held.
NOT_CONNECTED: Final = "This channel is not connected."
SWITCHED_OFF: Final = "This channel is switched off."
KEY_NOT_HELD: Final = "This channel's key is not in the vault."
VAULT_UNREADABLE: Final = "The vault could not be read, so this channel's list was not asked for."
UNREAD: Final = "The channel did not answer with its list."


def connected_problem(record: ChannelRecord | None, *, secret_held: bool) -> str:
    """Why a channel cannot carry the digest, or empty when it can. One order everywhere."""
    if record is None:
        return NOT_CONNECTED
    if not record.enabled:
        return SWITCHED_OFF
    if not secret_held:
        return KEY_NOT_HELD
    return ""


async def offer_of(
    record: ChannelRecord,
    *,
    lister: ConversationLister,
    secrets: ChannelSecrets,
    transport: ChannelTransport,
) -> ChannelOffer:
    """What one connected channel offers, read page by page through its own wire."""
    try:
        secret = await asyncio.to_thread(secrets.read, record.secret)
    except ChannelSecretsUnavailableError:
        return ChannelOffer(record.channel, (), VAULT_UNREADABLE)
    problem = connected_problem(record, secret_held=secret is not None)
    if problem or secret is None:
        return ChannelOffer(record.channel, (), problem or KEY_NOT_HELD)
    found: list[Offered] = []
    page = ""
    for _ in range(MAX_PAGES):
        try:
            request = lister.conversations_request(page=page, secret=secret, tenant=record.tenant)
            answer = await asyncio.to_thread(transport.read, request)
            rows, page = lister.conversations_page(answer)
        except ValueError as refused:
            return ChannelOffer(record.channel, tuple(found), str(refused) or UNREAD)
        found.extend(Offered(Destination(record.channel, cid), name) for cid, name in rows)
        if not page:
            break
    return ChannelOffer(record.channel, tuple(found))


async def offered(
    records: tuple[ChannelRecord, ...],
    *,
    secrets: ChannelSecrets,
    transport: ChannelTransport,
    wires: Callable[[], Mapping[Channel, object]] = channel_wires,
) -> tuple[ChannelOffer, ...]:
    """Every connected channel whose wire can list conversations, and what each offers.

    A channel whose wire cannot list is left out rather than offered empty: it is not a choice at
    all, and an empty entry would read as a list that happened to be empty today.
    """
    known = wires()
    found: list[ChannelOffer] = []
    for record in records:
        lister = known.get(record.channel)
        if not isinstance(lister, ConversationLister):
            continue
        found.append(await offer_of(record, lister=lister, secrets=secrets, transport=transport))
    return tuple(found)


def is_offered(choice: Destination, offers: tuple[ChannelOffer, ...]) -> bool:
    """Whether a choice is on the list the channels offer now. See the module docstring."""
    return any(one.destination == choice for offer in offers for one in offer.conversations)


def standing(
    saved: str, *, record: ChannelRecord | None, secret_held: bool
) -> tuple[Destination | None, str]:
    """The destination and why the digest cannot go there, or an empty reason when it can.

    Unset is a reason too, in words, because the Settings row shows it: the digest is off until
    somebody chooses.
    """
    chosen = destination_of(saved)
    if chosen is None:
        return None, "Off: nobody has chosen where the evening digest goes."
    if record is not None and record.channel is not chosen.channel:
        msg = "the record read is not the chosen channel's"
        raise ValueError(msg)
    problem = connected_problem(record, secret_held=secret_held)
    return chosen, (f"Stopped: {problem}" if problem else "")
