"""Which channels an agent is switched on for, as presses on the install.

An agent answers only on the channels an administrator switched on for it, and never on every
channel by default (`docs/requirements/register.json` OWN-7, ARC-A-171, OWN-56). Nothing stored a
switch, so every stored agent answered on every channel it could be addressed on. `0159` builds
this table, `0159b` switches the web page on for every agent that existed when it ran, and
`brain.ops.channel_switch_store` is the one writer after that.

**One row per press, never edited.** The newest row for an agent and a channel is whether it is
on. A channel no row names is off, which is the requirement itself: an agent nobody switched on
answers nowhere.

**Its trigger writes a `compose_change` ledger entry** with the channel and the direction, so a
switch and its record cannot be separated, the backfill's rows included.

**`switch_row` builds a row for every writer**: the page's switch, and the web page switched on in
the same transaction that makes an agent, by the draft publish and the install. One builder, so the
three cannot write a switch in different shapes.

Task ids: M39.2.4.1, M39.2.4.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.gate.context import Channel
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

AGENT_ID_CHARS: Final = 128
CHANNEL_CHARS: Final = 32
TRACE_ID_CHARS: Final = 128
REASON_CHARS: Final = 64
ENT_HASH_PATTERN: Final = r"^[0-9a-f]{32}$"
REASON_PATTERN: Final = r"^[a-z][a-z0-9_]{0,63}$"


class ChannelSwitchRow(Base):
    """`agent.channel_switch`. One channel switched on or off for one agent."""

    __tablename__ = "channel_switch"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    switched_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    entitlement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        Index("ix_channel_switch_agent_changed", "agent_id", "changed_at"),
        {"schema": "agent"},
    )


#: The web page, as the gate names the channel a signed-in browser asks on.
WEB_PAGE: Final = Channel.CONSOLE

#: The reason codes a switch is recorded with when nobody pressed a switch on the agent's page.
#: The web page switched on by the publisher of a new agent who left it ticked.
SWITCHED_ON_WHEN_PUBLISHED: Final = "switched_on_when_published"
#: The web page switched on by whoever installed or duplicated an agent with it ticked.
SWITCHED_ON_WHEN_MADE: Final = "switched_on_when_made"
#: `0159b`'s own rows, one per agent that existed when it ran, and the actor they are written by.
#: Held equal to the migration's.
ANSWERED_ON_THE_WEB_BEFORE_CHANNELS_EXISTED: Final = "answered_on_the_web_before_channels_existed"
BACKFILLED_BY: Final = "migration.0159b"


def switch_row(
    *,
    agent_id: str,
    channel: Channel,
    switched_on: bool,
    by: str,
    reason_code: str,
    ent_hash: str,
    trace_id: str,
    at: datetime | None,
) -> ChannelSwitchRow:
    """One switch, written in `by`'s name, which `0159`'s insert policy holds to the session's.

    `at` None leaves the instant to the database's clock, for a writer with no request instant.
    """
    row = ChannelSwitchRow(
        id=uuid.uuid4(),
        agent_id=agent_id,
        channel=channel.value,
        switched_on=switched_on,
        changed_by=by,
        reason_code=reason_code,
        entitlement_hash=ent_hash,
        trace_id=trace_id,
    )
    if at is not None:
        row.changed_at = at
    return row
