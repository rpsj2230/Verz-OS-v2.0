"""Whether a channel is working, read from what its deliveries say, for the Channels screen.

`brain.channels.adapter.ChannelAdapter.healthy` is the adapter's own answer, and every adapter in
this release answers it from a flag nothing sets, so it says an adapter exists rather than that
anything reached it. What an install actually knows about a channel is `ops.channel_delivery`:
every request received or refused and every message sent, refused or unanswered, with its reason.
This reads that into one of five states an administrator can act on (M10.1.4).

**A refusal of a stranger's request says nothing about the channel.** The events address takes
no sign-in, so anybody can post to it, and a request that fails its signature, is too large or
cannot be read is refused by a channel doing its job. Counting those as faults would let anybody
on the internet turn an administrator's screen red. So only a delivery that went through, or one
that failed for a reason on this side or the vendor's, decides the state, newest first; the rest
are shown in the deliveries list and decide nothing. See
`A_STRANGERS_REFUSED_REQUEST_SAYS_NOTHING_ABOUT_THE_CHANNEL`.

**The record decides before the deliveries do.** A channel with no record is not set up and one
switched off is off, whatever it did last week, because the question the screen answers is
whether a message sent now would be answered.

**A bound sender with nothing to answer them is a fault.** `not_answerable` is recorded when a
message from somebody bound arrived and no answerer is wired on the install, and the person who
sent it heard nothing. That is the channel failing its person, even though no vendor was asked.

Task ids: M10.1.4
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.ops.channel_store import ChannelRecord, DeliveryView
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause

#: Why most inbound refusals decide nothing.
A_STRANGERS_REFUSED_REQUEST_SAYS_NOTHING_ABOUT_THE_CHANNEL: Final = (
    "The events address takes no sign-in, so a request with a wrong signature, one too large and "
    "one that cannot be read are refused by a channel doing its job. Only a delivery that went "
    "through, or one that failed for a reason on this side or the vendor's, says whether the "
    "channel works, so nobody posting junk to the address can turn this screen red."
)

#: The reasons that are a fault of the channel, on this side or the vendor's.
FAULTS: Final[frozenset[RefusedBecause]] = frozenset(
    {
        RefusedBecause.NO_SECRET,
        RefusedBecause.VAULT_UNAVAILABLE,
        RefusedBecause.INCOMPLETE,
        RefusedBecause.UNSAFE_ADDRESS,
        RefusedBecause.VENDOR_REFUSED,
        RefusedBecause.VENDOR_UNAVAILABLE,
        RefusedBecause.NOT_ANSWERABLE,
    }
)

#: The outcomes that are a delivery that went through, by direction.
WENT_THROUGH: Final[Mapping[Direction, frozenset[DeliveryOutcome]]] = {
    Direction.INBOUND: frozenset({DeliveryOutcome.ACCEPTED, DeliveryOutcome.REDELIVERED}),
    Direction.OUTBOUND: frozenset({DeliveryOutcome.SENT}),
}


class ChannelHealthState(enum.StrEnum):
    """What the Channels screen says about one channel."""

    NOT_SET_UP = "not_set_up"
    SWITCHED_OFF = "switched_off"
    #: Switched on and nothing that decides anything has been recorded yet.
    QUIET = "quiet"
    WORKING = "working"
    FAILING = "failing"


#: What each state tells the administrator, in the words the screen shows.
TOLD: Final[Mapping[ChannelHealthState, str]] = {
    ChannelHealthState.NOT_SET_UP: "Not set up on this install. Nothing is received or sent on it.",
    ChannelHealthState.SWITCHED_OFF: "Switched off. It refuses every request and sends nothing.",
    ChannelHealthState.QUIET: (
        "Switched on, and nothing has been received or sent on it yet. Send a test message to "
        "prove it can send."
    ),
    ChannelHealthState.WORKING: (
        "Working. The newest delivery that says anything about it went through."
    ),
    ChannelHealthState.FAILING: (
        "Failing. The newest delivery that says anything about it did not go through, for the "
        "reason shown. Messages sent now may not arrive."
    ),
}


@dataclass(frozen=True)
class ChannelHealth:
    """One channel's state, and the deliveries it was read from. Nothing a message said."""

    health: ChannelHealthState
    told: str
    #: The newest request received and accepted, or None.
    last_received_at: datetime | None
    #: The newest message the vendor accepted, or None.
    last_sent_at: datetime | None
    #: The newest delivery that failed for a fault, or None. Its reason is from a closed list.
    last_fault: DeliveryView | None


def is_fault(one: DeliveryView) -> bool:
    """A delivery that failed for a reason on this side or the vendor's."""
    reason = one.entry.reason
    return reason is not None and reason in FAULTS


def went_through(one: DeliveryView) -> bool:
    """A request accepted, or a message the vendor accepted."""
    return one.entry.outcome in WENT_THROUGH[one.entry.direction]


def channel_health(
    record: ChannelRecord | None, deliveries: Iterable[DeliveryView]
) -> ChannelHealth:
    """This channel's state from its record and its deliveries, newest first (M10.1.4).

    See the module docstring for the order: the record, then the newest delivery that decides.
    """
    newest = sorted(deliveries, key=lambda one: one.recorded_at, reverse=True)
    received = next(
        (
            one.recorded_at
            for one in newest
            if one.entry.direction is Direction.INBOUND and went_through(one)
        ),
        None,
    )
    sent = next(
        (
            one.recorded_at
            for one in newest
            if one.entry.direction is Direction.OUTBOUND and went_through(one)
        ),
        None,
    )
    fault = next((one for one in newest if is_fault(one)), None)
    if record is None:
        health = ChannelHealthState.NOT_SET_UP
    elif not record.enabled:
        health = ChannelHealthState.SWITCHED_OFF
    else:
        deciding = next((one for one in newest if went_through(one) or is_fault(one)), None)
        if deciding is None:
            health = ChannelHealthState.QUIET
        elif went_through(deciding):
            health = ChannelHealthState.WORKING
        else:
            health = ChannelHealthState.FAILING
    return ChannelHealth(
        health=health,
        told=TOLD[health],
        last_received_at=received,
        last_sent_at=sent,
        last_fault=fault,
    )
