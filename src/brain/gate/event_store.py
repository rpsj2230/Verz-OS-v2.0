"""Claiming an inbound channel message, so a redelivered one is not answered twice.

The decision is the database's: `gate.channel_event`'s primary key is the unique index on
`(channel, external_id)`, and the insert does nothing on a conflict. `first_delivery` returns
whether this call's row went in, so exactly one of two concurrent deliveries is told it is the
first, whichever order they commit in. A read-then-insert would let both read "not seen".

It does not commit, for `brain.ops.telemetry_store.record`'s reason: the caller owns the
transaction, and a claim should be committed with whatever the caller does about it.

Task ids: M3.2.2
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.gate.ingress import ChannelEvent
from brain.tables.channel_event import EXTERNAL_ID_CHARS, ChannelEventRow


class ExternalIdTooLongError(ValueError):
    """An external id longer than the column. Refused rather than truncated, because two ids
    sharing a prefix would truncate to one key and the second message would be dropped."""


async def first_delivery(session: AsyncSession, event: ChannelEvent) -> bool:
    """True when this is the first time this channel delivered this message. Does not commit."""
    if len(event.external_id) > EXTERNAL_ID_CHARS:
        msg = (
            f"a {event.channel} external id of {len(event.external_id)} characters is longer "
            f"than the {EXTERNAL_ID_CHARS} the dedupe key holds"
        )
        raise ExternalIdTooLongError(msg)
    channel, external_id = event.dedupe_key
    claimed = await session.execute(
        insert(ChannelEventRow)
        .values(channel=channel, external_id=external_id, received_at=event.received_at)
        .on_conflict_do_nothing(index_elements=["channel", "external_id"])
        .returning(ChannelEventRow.external_id)
    )
    return claimed.first() is not None
