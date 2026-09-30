"""The webhooks a platform would send here, and how far each one's check has got.

The Webhooks screen said "no channel receives a webhook" and one sentence for all of them, and the
sentence was wrong in the direction that matters: it said each channel had its way of checking a
request written and tested, and two of them have nothing. So this is the list the screen draws,
one row per channel a platform would call in on, each saying whether the check that a request
really came from that platform is written, which function it is, and what it needs.

**Three facts per channel, and two of them vary.** Whether the check is written is different per
channel. Whether this release receives a channel at all is `receiving`'s answer, read off the
wires `brain.channels.adapter.channel_wires` discovers, and a channel it names is received at
`CHANNEL_EVENTS_PATH` only while its record is switched on and its secret is held, which is the
install's own state and is shown on the channel's record rather than here. The screen states which
channels are received once above the list, in `brain.ops.webhook_admin.receiving_told`, rather
than leaving it out: a list that said only "check written" reads as channels that work.
`test_inbound_webhooks` holds that sentence and the one receiving route against the application's
own routes, so a channel given a receiver moves the sentence with it.

**A written check is named by the function, and the name is resolved, not trusted.** A row that
said "written" beside a function renamed a month ago would be the same claim the old sentence
made. Every named check is imported and found by a test, and every channel an adapter declares
has a row, so a channel added without one fails rather than being left off the screen.

Rejected: reading the verification state out of the adapters. `ChannelCapabilities` says what an
adapter can carry and nothing about inbound requests, and widening it would put a fact about a
module's functions into a value each adapter declares by hand, which is the copy that drifts.

Task ids: M27.8.12, M10.2.1
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from brain.gate.context import Channel

#: Where a platform posts a channel's messages, under the install's own origin. Held equal to
#: `brain.channel_routes.EVENTS_PATH` by `tests/unit/test_inbound_webhooks.py`.
CHANNEL_EVENTS_PATH: Final = "/api/v1/channels/{channel}/events"


def receiving() -> frozenset[Channel]:
    """The channels this release receives: those with a wire in `brain.channels`.

    Read from the wires rather than listed, so the screen cannot name a channel that has no
    receiver or leave out one that has. Imported inside, because the channel modules are the
    product's heaviest imports and this module is read by a screen that may never ask.
    """
    from brain.channels.adapter import channel_wires

    return frozenset(channel_wires())


class Verification(enum.StrEnum):
    """How far the check that a request came from its platform has got."""

    #: Written and tested. Whether a route calls it on every request is `receiving`'s answer.
    WRITTEN = "written"
    #: Not written: a request claiming to be from this platform could not be told from a forgery.
    NOT_WRITTEN = "not_written"
    #: Arrives through a mail server, not as a request to an address this install serves.
    NOT_A_WEBHOOK = "not_a_webhook"


@dataclass(frozen=True)
class InboundChannel:
    """One channel a platform would call in on, and the state of the check for it.

    `check` is `module:function` and is empty exactly when nothing is written, which the
    constructor holds.
    """

    channel: Channel
    verification: Verification
    check: str
    how: str

    def __post_init__(self) -> None:
        written = self.verification is Verification.WRITTEN
        if written != bool(self.check):
            msg = (
                f"{self.channel.value}: a written check names its function and an unwritten one "
                "names none, so the screen cannot point at a function that is not there"
            )
            raise ValueError(msg)
        if not self.how.strip():
            msg = f"{self.channel.value}: every row says how the platform's request is checked"
            raise ValueError(msg)


#: Every channel a platform would call in on, in the order the screen lists them.
INBOUND: Final[tuple[InboundChannel, ...]] = (
    InboundChannel(
        channel=Channel.EMAIL,
        verification=Verification.WRITTEN,
        check="brain.channels.webhook:verify",
        how=(
            "The company's mail service receives the message and turns away mail that fails the "
            "sender's DMARC policy; a script there posts it here with that verdict, signed with "
            "the channel's secret over the time and the exact bytes, the webhook channel's "
            "construction. The check refuses a stale or unsigned request, and mail whose verdict "
            "is not a pass is treated as from nobody. It is received at its channel's events "
            "address while its record is switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.LARK,
        verification=Verification.WRITTEN,
        check="brain.channels.lark:verify_event",
        how=(
            "Lark signs each event with the app's Encrypt Key over the time, a nonce and the exact "
            "bytes, encrypts it with the same key and puts the Verification Token inside; the "
            "check refuses an unencrypted body, a signature that is not the key's, a request more "
            "than five minutes old and a token that is not the app's. It is received at its "
            "channel's events address while its record is switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.SLACK,
        verification=Verification.WRITTEN,
        check="brain.channels.slack:verify",
        how=(
            "Slack signs each request with the app's signing secret over the time and the exact "
            "bytes sent; the check refuses a request more than five minutes old or signed with "
            "anything else. It is received at its channel's events address while its record is "
            "switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.TEAMS,
        verification=Verification.WRITTEN,
        check="brain.channels.teams:verified_activity",
        how=(
            "Microsoft sends a token it signed; the check verifies it against Microsoft's "
            "published keys, the bot's app id and the one tenant the install is pinned to. It is "
            "received at its channel's events address while its record is switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.TELEGRAM,
        verification=Verification.WRITTEN,
        check="brain.channels.telegram:verified_update",
        how=(
            "Telegram repeats a secret the install made from the bot token and named when it "
            "registered its address; the check compares it in constant time. It is received at "
            "its channel's events address while its record is switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.WEBHOOK,
        verification=Verification.WRITTEN,
        check="brain.channels.webhook:verify",
        how=(
            "A system of the company's own signs each request with the channel's secret over the "
            "time and the exact bytes, the same construction this install signs its own deliveries "
            "with; the check refuses a stale request, and a repeated message is claimed once. It "
            "is received at its channel's events address while its record is switched on."
        ),
    ),
    InboundChannel(
        channel=Channel.WHATSAPP,
        verification=Verification.NOT_WRITTEN,
        check="",
        how=(
            "Meta signs each request with the app secret. Nothing here checks that signature yet, "
            "so a request claiming to be from WhatsApp could not be told apart from a forged one."
        ),
    ),
)
