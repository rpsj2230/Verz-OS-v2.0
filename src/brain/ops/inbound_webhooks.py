"""The webhooks a platform would send here, and how far each one's check has got.

The Webhooks screen said "no channel receives a webhook" and one sentence for all of them, and the
sentence was wrong in the direction that matters: it said each channel had its way of checking a
request written and tested, and two of them have nothing. So this is the list the screen draws,
one row per channel a platform would call in on, each saying whether the check that a request
really came from that platform is written, which function it is, and what it needs.

**Three facts per channel, and only one of them varies today.** Whether the check is written is
different per channel. Whether a secret is held for it, and whether any address receives it, are
the same answer everywhere, no, and the screen states that answer once above the list, in
`brain.ops.webhook_admin.NO_CHANNEL_RECEIVES_A_WEBHOOK`, rather than leaving it out: a list that
said only "check written" reads as channels that work. `test_inbound_webhooks` holds the route half
against the application's own routes, so the day a receiving route arrives the sentence has to
move.

**A written check is named by the function, and the name is resolved, not trusted.** A row that
said "written" beside a function renamed a month ago would be the same claim the old sentence
made. Every named check is imported and found by a test, and every channel an adapter declares
has a row, so a channel added without one fails rather than being left off the screen.

Rejected: reading the verification state out of the adapters. `ChannelCapabilities` says what an
adapter can carry and nothing about inbound requests, and widening it would put a fact about a
module's functions into a value each adapter declares by hand, which is the copy that drifts.

Task ids: M27.8.12
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from brain.gate.context import Channel


class Verification(enum.StrEnum):
    """How far the check that a request came from its platform has got."""

    #: Written and tested, and called by nothing that receives, because nothing receives.
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
        verification=Verification.NOT_A_WEBHOOK,
        check="",
        how=(
            "Mail arrives through a mail server, which records whether the sender passed its "
            "authentication checks; the adapter takes that verdict from the server, never from the "
            "message, and treats mail that did not pass as from nobody."
        ),
    ),
    InboundChannel(
        channel=Channel.LARK,
        verification=Verification.NOT_WRITTEN,
        check="",
        how=(
            "Lark signs or encrypts each event with keys from the app's settings. Nothing here "
            "checks either yet, so an event claiming to be from Lark could not be told apart from "
            "a forged one."
        ),
    ),
    InboundChannel(
        channel=Channel.SLACK,
        verification=Verification.WRITTEN,
        check="brain.channels.slack:verify",
        how=(
            "Slack signs each request with the app's signing secret over the time and the exact "
            "bytes sent; the check refuses a request more than five minutes old or signed with "
            "anything else."
        ),
    ),
    InboundChannel(
        channel=Channel.TEAMS,
        verification=Verification.WRITTEN,
        check="brain.channels.teams:verified_activity",
        how=(
            "Microsoft sends a token it signed; the check verifies it against Microsoft's "
            "published keys, the bot's app id and the one tenant the install is pinned to."
        ),
    ),
    InboundChannel(
        channel=Channel.TELEGRAM,
        verification=Verification.WRITTEN,
        check="brain.channels.telegram:verified_update",
        how=(
            "Telegram repeats a secret token chosen when the webhook is set; the check compares it "
            "in constant time and refuses a configured token shorter than 32 characters."
        ),
    ),
    InboundChannel(
        channel=Channel.WEBHOOK,
        verification=Verification.WRITTEN,
        check="brain.channels.webhook:verify",
        how=(
            "A system of the company's own signs each request with a shared secret over the time "
            "and the exact bytes, the same construction this install signs its own deliveries "
            "with; the check refuses a stale request and a repeated one."
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
