"""The shared conversations the bot is in, and the agent installed into each (M39.2.4.4).

`brain.console.agent_tabs` decided what a group install is (`GroupInstall`: an agent, a channel and
the conversation's own reference, and nothing that could be a grant) and refused one on any surface
that does not declare `Feature.GROUP_INSTALL`. Nothing could hold one. `0205` builds both tables.

**`ops.channel_room` is a vendor fact, kept as the vendor says it.** A room is a conversation the
bot was added to, read off the vendor's own event (Lark's `im.chat.member.bot.added_v1`) with the
name the vendor gave it, and closed when the bot is removed. Nobody chooses a room by typing its
reference, which is a vendor id nobody can read; the console offers the rooms the bot is in. It is
not ledgered: the bot being added to a conversation changes nobody's access, and every answer there
is still decided at `brain.channels.room.floor`.

**`agent.group_install` is the decision, and it is ledgered.** One live install per room, so a
message in it is answered by one agent; installing names who did it, removing names who did that,
and the row's trigger writes `AuditRecorder.compose_change`'s entry for each, with the part
`group` and the room's reference. The row carries no reach of any kind, which is
`agent_tabs.INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM` as a shape.

Task ids: M39.2.4.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, PrimaryKeyConstraint, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from brain.db import Base
from brain.gate.context import Channel
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide an agent's identifier may be, matching `brain.tables.attachment.AGENT_ID_CHARS`.
AGENT_ID_CHARS: Final = 128
CHANNEL_CHARS: Final = 16
#: A vendor's conversation id: Lark's `oc_` ids, Slack's channel ids. Held to the ledger's own
#: identifier grammar, because the reference is written into a ledger entry's details.
ROOM_REF_CHARS: Final = 128
ROOM_REF_PATTERN: Final = r"^[A-Za-z0-9_.@-]{1,128}$"
#: The name the vendor gave the conversation, for a person to choose it by.
ROOM_NAME_CHARS: Final = 200


class ChannelRoomRow(Base):
    """`ops.channel_room`. One conversation the bot was added to, until it was removed."""

    __tablename__ = "channel_room"

    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    room_ref: Mapped[str] = mapped_column(String(ROOM_REF_CHARS), nullable=False)
    name: Mapped[str] = mapped_column(
        String(ROOM_NAME_CHARS), nullable=False, server_default=text("''")
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("channel", "room_ref"),
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint(f"room_ref ~ '{ROOM_REF_PATTERN}'", name="room_ref_shape"),
        {"schema": "ops"},
    )


class GroupInstallRow(Base):
    """`agent.group_install`. One agent installed into one room, until it was removed."""

    __tablename__ = "group_install"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    room_ref: Mapped[str] = mapped_column(String(ROOM_REF_CHARS), nullable=False)
    installed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )
    removed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint(f"room_ref ~ '{ROOM_REF_PATTERN}'", name="room_ref_shape"),
        CheckConstraint("length(btrim(agent_id)) > 0", name="names_an_agent"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_names_who_and_when"
        ),
        Index(
            "uq_group_install_one_agent_per_room",
            "channel",
            "room_ref",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("ix_group_install_agent_id", "agent_id"),
        {"schema": "agent"},
    )
