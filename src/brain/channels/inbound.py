"""What every chat channel does with a message before anything answers it: claim, then address.

Every adapter turns what arrived into a `brain.gate.ingress.ChannelEvent` through
`ChannelAdapter.normalise`, and nothing after that step asked whether the message had been seen
before. A provider that redelivers on a timeout, which is every webhook provider, would then be
answered twice, and a message asking for a side effect would have it done twice. This is the one
step between an adapter and the answer, so no adapter can reach the gate without it.

**The claim is the database's.** `brain.gate.event_store.first_delivery` inserts the dedupe key and
reports whether its row went in; a redelivery is refused by the primary key of
`gate.channel_event`, whichever of two concurrent deliveries commits first (M3.2.2). A message that
is not the first delivery comes back as None, and the caller answers nothing.

**A chat addresses an agent with a mention that opens the message (M3.9.8).**
`brain.gate.addressing.from_mention` takes a leading `@agent_id` off the question, and only a
leading one, for the reason that module gives about quoted text choosing an agent. The id goes to
`brain.gate.select.select_agent` as a name like any other; nothing here decides who may use it.

What does not exist yet, stated: no inbound HTTP route for a chat channel is served by this
application, so no adapter answers a message today. The route that is built for one calls this
first, and `tests/unit/test_channel_inbound.py` holds the order.

Task ids: M3.2.2, M3.9.8
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from brain.channels.adapter import ChannelAdapter
from brain.gate.addressing import Address, from_mention
from brain.gate.event_store import first_delivery
from brain.gate.ingress import ChannelEvent


@dataclass(frozen=True)
class Inbound:
    """A message claimed as its first delivery, and what it asks of whom."""

    event: ChannelEvent
    address: Address


async def claim(session: AsyncSession, adapter: ChannelAdapter, raw: object) -> Inbound | None:
    """The message as the gate reads it, or None when this channel delivered it before.

    Normalised first, so a payload the adapter refuses is refused before anything is written;
    claimed second, so the dedupe key is the adapter's own; addressed last, from the text the
    adapter extracted. Does not commit: the caller owns the transaction, for
    `first_delivery`'s reason.
    """
    event = adapter.normalise(raw)
    if not await first_delivery(session, event):
        return None
    return Inbound(event=event, address=from_mention(event.text))
