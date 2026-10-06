"""The rooms the bot is in, and the agent installed into each, read and written (M39.2.4.4).

`brain.console.agent_tabs.install_to_group` decides whether an install may be made and
`brain.channels.room` decides what may be said in a room; this holds the statements and neither
rule. `brain.tables.group_install` holds the argument for each column.

**A room is noted from the vendor's verified event and from nothing else.** `note` is called by the
events route with a `RoomChange` a wire read off a signed request, so a room exists here exactly
when the vendor said the bot was added to it, and stops when the vendor said it was removed.

**An install is written in the session's own name, and only into a room the bot is in.** The insert
reads the room inside the same transaction and writes nothing when it is not live, and `0205`'s
partial unique index refuses a second live install in one room, so one message has one agent to
answer it. Every write runs `brain.tables.audit.attributed_to` first and names the session's
principal, which `0205`'s policies compare and its trigger records.

Task ids: M39.2.4.4
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.adapter import RoomChange
from brain.gate.context import Channel
from brain.identity.role_store import Attribution
from brain.tables.audit import attributed_to
from brain.tables.group_install import ChannelRoomRow, GroupInstallRow

#: The most rooms or installs one listing reads. A company is in a few dozen group chats.
MOST_ROOMS_READ: Final = 500


@dataclass(frozen=True)
class Room:
    """One conversation the bot is in, as the vendor named it."""

    channel: Channel
    room_ref: str
    name: str


@dataclass(frozen=True)
class Installed:
    """One live install, with the room's name and whether the bot is still in it."""

    install_id: uuid.UUID
    agent_id: str
    channel: Channel
    room_ref: str
    name: str
    present: bool
    installed_at: datetime


@dataclass(frozen=True)
class StoredGroupInstalls:
    """`ops.channel_room` and `agent.group_install` over the application's pool."""

    sessions: async_sessionmaker[AsyncSession]

    async def _open(self, session: AsyncSession, by: Attribution) -> None:
        for statement in attributed_to(
            actor_id=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
        ):
            await session.execute(statement)
        await session.execute(
            text("SELECT set_config('app.principal_id', :by, true)").bindparams(by=by.actor)
        )

    async def note(self, channel: Channel, change: RoomChange, at: datetime) -> None:
        """Keep a room the bot joined, or close one it left, as the vendor's event said."""
        async with self.sessions() as session, session.begin():
            if change.joined:
                statement = pg_insert(ChannelRoomRow).values(
                    channel=channel.value,
                    room_ref=change.conversation_id,
                    name=change.name,
                    joined_at=at,
                    left_at=None,
                )
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["channel", "room_ref"],
                        set_={"name": change.name, "joined_at": at, "left_at": None},
                    )
                )
            else:
                await session.execute(
                    update(ChannelRoomRow)
                    .where(
                        ChannelRoomRow.channel == channel.value,
                        ChannelRoomRow.room_ref == change.conversation_id,
                        ChannelRoomRow.left_at.is_(None),
                    )
                    .values(left_at=at)
                )

    async def rooms(self, channels: Sequence[Channel]) -> list[Room]:
        """The rooms the bot is in on these channels and no agent is installed into."""
        if not channels:
            return []
        taken = select(GroupInstallRow.id).where(
            GroupInstallRow.channel == ChannelRoomRow.channel,
            GroupInstallRow.room_ref == ChannelRoomRow.room_ref,
            GroupInstallRow.removed_at.is_(None),
        )
        statement = (
            select(ChannelRoomRow)
            .where(
                ChannelRoomRow.channel.in_([one.value for one in channels]),
                ChannelRoomRow.left_at.is_(None),
                ~taken.exists(),
            )
            .order_by(ChannelRoomRow.name, ChannelRoomRow.room_ref)
            .limit(MOST_ROOMS_READ)
        )
        async with self.sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [
            Room(channel=Channel(row.channel), room_ref=row.room_ref, name=row.name) for row in rows
        ]

    async def installs_of(self, agent_id: str) -> list[Installed]:
        """This agent's live installs, each with its room's name and whether the bot is there."""
        statement = (
            select(GroupInstallRow, ChannelRoomRow.name, ChannelRoomRow.left_at)
            .join(
                ChannelRoomRow,
                and_(
                    ChannelRoomRow.channel == GroupInstallRow.channel,
                    ChannelRoomRow.room_ref == GroupInstallRow.room_ref,
                ),
                isouter=True,
            )
            .where(GroupInstallRow.agent_id == agent_id, GroupInstallRow.removed_at.is_(None))
            .order_by(GroupInstallRow.installed_at)
            .limit(MOST_ROOMS_READ)
        )
        async with self.sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            Installed(
                install_id=row.id,
                agent_id=row.agent_id,
                channel=Channel(row.channel),
                room_ref=row.room_ref,
                name=name or "",
                present=name is not None and left_at is None,
                installed_at=row.installed_at,
            )
            for row, name, left_at in rows
        ]

    async def installed_in(self, channel: Channel, room_ref: str) -> str | None:
        """The agent installed into this room, or None."""
        statement = select(GroupInstallRow.agent_id).where(
            GroupInstallRow.channel == channel.value,
            GroupInstallRow.room_ref == room_ref,
            GroupInstallRow.removed_at.is_(None),
        )
        async with self.sessions() as session:
            found: str | None = (await session.execute(statement)).scalar_one_or_none()
            return found

    async def install(
        self, *, agent_id: str, channel: Channel, room_ref: str, by: Attribution
    ) -> Installed | None:
        """Install this agent into a room the bot is in, or None where nothing was written."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                room = (
                    await session.execute(
                        select(ChannelRoomRow).where(
                            ChannelRoomRow.channel == channel.value,
                            ChannelRoomRow.room_ref == room_ref,
                            ChannelRoomRow.left_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if room is None:
                    return None
                stored: GroupInstallRow = (
                    await session.execute(
                        pg_insert(GroupInstallRow)
                        .values(
                            agent_id=agent_id,
                            channel=channel.value,
                            room_ref=room_ref,
                            installed_by=by.actor,
                        )
                        .returning(GroupInstallRow)
                    )
                ).scalar_one()
                return Installed(
                    install_id=stored.id,
                    agent_id=stored.agent_id,
                    channel=channel,
                    room_ref=stored.room_ref,
                    name=room.name,
                    present=True,
                    installed_at=stored.installed_at,
                )
        except (IntegrityError, DBAPIError):
            # A room that already has an agent, which `0205`'s unique index refuses.
            return None

    async def remove(self, install_id: uuid.UUID, *, agent_id: str, by: Attribution) -> bool:
        """Remove one of this agent's live installs; False where there was none to remove."""
        async with self.sessions() as session, session.begin():
            await self._open(session, by)
            removed = (
                await session.execute(
                    update(GroupInstallRow)
                    .where(
                        GroupInstallRow.id == install_id,
                        GroupInstallRow.agent_id == agent_id,
                        GroupInstallRow.removed_at.is_(None),
                    )
                    .values(removed_by=by.actor, removed_at=func.statement_timestamp())
                    .returning(GroupInstallRow.id)
                )
            ).scalar_one_or_none()
            return removed is not None
