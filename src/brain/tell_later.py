"""Telling one person something later, in the chat they last used, at the reach they hold then.

Everything the Brain says in a chat until now was a reply: the person wrote, and the answer went
back to where they wrote from, at the reach the request was admitted at. Some things a person has to
be told after that request has gone. A question handed to somebody who never picked it up is the
first: the asker was told it had gone to a queue and nothing since, and the only place the expiry
showed was a list in the web application they had no reason to open. This module is the one sender
for that kind of message, and its first caller is `brain.escalation_told`.

**The address is their own, on the channel they last wrote on (needs-rupash 118).** A binding keeps
its person's own address on Lark, Slack and email (`brain.ops.binding_store.ADDRESS_KEPT_ON`), and
`StoredAddresses.last_used` names the one they wrote on last, kept to the hour. The message goes to
that address through the wire's own `person_address`, which is their conversation with the bot and
never a room: a thing told to one person later has no business in a group they happened to ask in.
Nobody is written to on a channel an administrator has switched off, on a wire that cannot address a
person, or at all when they have linked no such channel. See
`A_LATER_MESSAGE_GOES_TO_THE_PERSON_ALONE`.

**The reach is theirs as it stands when it leaves.** The message names its recipient and the digest
of their reach now, and `brain.channels.outbound.deliver` loads their reach again at the moment of
sending and refuses the message if it moved or lapsed, which is the rule every reply already keeps
(M10.4.5). A person who has left is told nothing, because an expired reach sends nothing.

**Once, whatever retries it.** The message is keyed by the person and an intent the caller names,
through the operation ledger every send uses, so two web processes, a restart or a second pass of
the caller's loop send it once. The caller chooses the key, because only it knows what makes two
messages the same message.

**What the person chose is honoured for the two kinds of message quiet hours cover** (M40.5.2.2,
M40.5.2.4). A digest or an automation notice names its kind, and `held_by` then asks the person's
own settings: a channel they made a statement about that does not list the kind gets nothing of it,
and inside their quiet hours it waits, which the caller's next pass finds out because nothing was
sent under the intent. An approval is never held, and a channel they said nothing about is written
to as before, because switching every existing person's digests off on the day a setting appears
would be a decision about all of them made by the person who added the table. See
`A_PERSON_WHO_SAID_NOTHING_IS_WRITTEN_TO_AS_BEFORE`.

Rejected: sending to every channel the person has linked. It is three messages for one fact, and the
one they read last is the one they would have been told on.

Task ids: M8.3.4, M40.5.2.2, M40.5.2.4
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime, tzinfo
from typing import Final, Protocol

from starlette.requests import Request

from brain.channels.adapter import PersonWire, channel_wires
from brain.channels.outbound import Delivered, Outgoing
from brain.gate.context import Channel
from brain.gate.resolve import EntitlementStore
from brain.install import InstallError
from brain.locale import time_zone
from brain.member.connections import NotificationKind, may_deliver
from brain.member.preferences import Preferences
from brain.ops.binding_store import ADDRESS_KEPT_ON
from brain.ops.channel_store import ChannelRecord, ChannelRecords
from brain.ops.idempotency import Intent
from brain.ops.member_preference_store import StoredPreferences

# ------------------------------------------------------------------ written-down reasons
#: Why a message told later goes to the person's own conversation and never to a room.
A_LATER_MESSAGE_GOES_TO_THE_PERSON_ALONE: Final = (
    "A reply goes back to where the person wrote, which may be a group they asked in. A message "
    "told later has no request behind it and nobody present to have asked for it in front of "
    "others, so it goes to the person's own conversation with the bot on the channel they last "
    "wrote on, at the address their binding keeps, and to nobody else."
)


#: Why an unstated preference is not read as "nothing".
A_PERSON_WHO_SAID_NOTHING_IS_WRITTEN_TO_AS_BEFORE: Final = (
    "`brain.member.connections.wants` reads an absent preference as wanting nothing, which is the "
    "quiet default for a screen. A sender that read it so would stop every person's digest the day "
    "this was added, so a channel is held back only for a person who said something about it."
)


class Held(enum.StrEnum):
    """Why a message told later is not sent now. Two, and neither names a person."""

    #: The person said what they want on this channel and this kind is not in it.
    NOT_WANTED = "not_wanted"
    #: It is inside their quiet hours, and waits for the next pass.
    QUIET_HOURS = "quiet_hours"


def held_by(
    preferences: Preferences,
    channel: Channel,
    kind: NotificationKind,
    at: datetime,
    zone: tzinfo,
) -> Held | None:
    """Whether this person's own settings hold back a message of `kind` on `channel` at `at`.

    `at` is turned into the install's zone for the person, because quiet hours are wall clock and
    `QuietHours.contains` compares an aware time in the zone they were typed in. An approval is
    never held: `may_deliver` is the one place that says so.
    """
    said = preferences.says(channel)
    if kind is not NotificationKind.APPROVAL and said and not preferences.wants(channel, kind):
        return Held.NOT_WANTED
    if not may_deliver(kind, preferences.quiet, at.astimezone(zone)):
        return Held.QUIET_HOURS
    return None


def _zone() -> tzinfo:
    """The install's zone, or UTC on an install that has not said one."""
    try:
        return time_zone()
    except (InstallError, ValueError):
        return UTC


async def hold_for(
    request: Request, person_id: str, kind: NotificationKind, *, now: datetime
) -> Held | None:
    """Whether this person's settings hold a message of `kind` back now, on the chat they last used.

    None for somebody with no address kept, which is `planned_for`'s business, and for a process
    with no database.
    """
    # Imported here: `brain.channel_routes` imports modules that will call this one.
    from brain.channel_routes import addresses_of
    from brain.routing_routes import sessions_of

    addresses, sessions = addresses_of(request), sessions_of(request)
    if addresses is None or sessions is None:
        return None
    found = await addresses.last_used(person_id)
    if found is None:
        return None
    settings = await StoredPreferences(sessions).of(person_id)
    return held_by(settings, found[0], kind, now, _zone())


class LastUsedAddresses(Protocol):
    """Where the channel a person last used, and their address on it, is read.

    `brain.ops.binding_store.StoredAddresses`.
    """

    async def last_used(self, principal_id: str) -> tuple[Channel, str] | None:
        """The channel this person last wrote on and their own address there, or None."""
        ...


async def planned_for(
    person_id: str,
    text: str,
    *,
    intent_ref: str,
    addresses: LastUsedAddresses,
    records: ChannelRecords,
    reach: EntitlementStore,
    now: datetime,
) -> tuple[Outgoing, ChannelRecord] | None:
    """The one message to this person and the channel record it goes out on, or None.

    None, and nothing sent, for somebody with no address kept, on a channel not switched on, on a
    wire that cannot address a person, or whose reach has lapsed. See
    `A_LATER_MESSAGE_GOES_TO_THE_PERSON_ALONE`.
    """
    found = await addresses.last_used(person_id)
    if found is None:
        return None
    channel, address = found
    if channel not in ADDRESS_KEPT_ON:
        # The store names no other; refused here too, so a second store cannot widen it.
        return None
    record = await records.get(channel)
    if record is None or not record.enabled:
        return None
    # Typed as an object: whether a wire can address a person is a question about its class, as
    # `brain.approval_cards` asks of a card.
    wire: object = channel_wires().get(channel)
    if not isinstance(wire, PersonWire):
        return None
    current = await reach.load(person_id, now)
    if current.is_expired(now):
        return None
    return (
        Outgoing(
            channel=channel,
            to=wire.person_address(address),
            intent=Intent(principal_id=person_id, intent_ref=intent_ref),
            text=text,
            recipient=person_id,
            planned_hash=current.ent_hash(),
        ),
        record,
    )


async def tell(
    request: Request,
    person_id: str,
    text: str,
    *,
    intent_ref: str,
    now: datetime,
    kind: NotificationKind | None = None,
) -> Delivered | None:
    """Tell one person `text` in the chat they last used, once for `intent_ref`, or nothing.

    `kind`, when the caller names one, lets the person's own settings hold the message back; see
    `held_by`. A caller that names none is told as before.

    Through the events route's own stores and its `deliver`, so the message is keyed, sent and
    recorded as every reply is. None when nothing was planned; see `planned_for`.
    """
    # Imported here: `brain.channel_routes` imports modules that will call this one.
    from brain.channel_routes import _deliver, addresses_of, reach_of, records_of

    addresses = addresses_of(request)
    if addresses is None:
        return None
    if kind is not None and await hold_for(request, person_id, kind, now=now) is not None:
        return None
    planned = await planned_for(
        person_id,
        text,
        intent_ref=intent_ref,
        addresses=addresses,
        records=records_of(request),
        reach=reach_of(request),
        now=now,
    )
    if planned is None:
        return None
    outgoing, record = planned
    return await _deliver(request, outgoing, record, now)
