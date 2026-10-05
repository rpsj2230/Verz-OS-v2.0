"""Send the evening digest to: the one setting that says where the digest goes, read and chosen.

`brain.ops.digest_destination` holds the rules and this is the route over them. `GET` answers the
current choice, whether the digest can go there and why not when it cannot, and what every
connected channel offers now. `PUT` saves a choice, and only one that is on the list at that
moment, so a person picks a conversation and never types an id; `off` stops the digest. The write
is the Settings screen's own: the same authority, `admin:install_setting` over everything, the
same attribution before the write so `0059`'s trigger records who changed it, and the same row in
`ops.setting` that outranks the environment (`brain.install.value_of`).

**Asked before the channels are.** A caller without the authority is refused before a record is
read or a vendor asked, with the Settings screen's own refusal, so the route says nothing to a
stranger about which channels this install has connected.

**The list is asked for on every read and every save.** A cached list would offer a group the bot
has since been removed from, and a save checked against it would accept the one choice that posts
nowhere.

Task ids: M38.3.3.1, M38.3.3.4
"""

from __future__ import annotations

import asyncio
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.channel_routes import records_of, secrets_of, transport_of
from brain.core.errors import Absent, Failed
from brain.gate.context import Channel
from brain.install import hold_saved, value_of
from brain.ops.channel_store import ChannelSecretsUnavailableError
from brain.ops.digest_destination import (
    A_DESTINATION_IS_CHOSEN_FROM_WHAT_THE_CHANNEL_OFFERS,
    DESTINATION_SETTING,
    UNSET,
    Destination,
    is_offered,
    offered,
    standing,
)
from brain.ops.install_settings import load, save
from brain.routing_routes import sessions_of
from brain.settings_routes import may_configure
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: Where the destination is read and chosen.
DESTINATION_PATH: Final = "/digest/destination"

router = APIRouter(prefix=API_PREFIX, tags=["install"])


class ConversationView(BaseModel):
    """One conversation a channel offers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    conversation: str
    name: str


class ChannelOfferView(BaseModel):
    """What one connected channel offers, or why nothing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    conversations: tuple[ConversationView, ...]
    why_none: str


class DestinationPage(BaseModel):
    """The choice, whether the digest can go there, and what may be chosen now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str | None
    conversation: str | None
    #: Empty when the digest can go where it is pointed; otherwise the sentence saying why not.
    stopped_because: str
    offers: tuple[ChannelOfferView, ...]


class ChooseAsked(BaseModel):
    """A choice: a channel and a conversation it offered, or off."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    off: bool = False
    channel: str = Field(default="", max_length=40)
    conversation: str = Field(default="", max_length=200)


def _not_answerable() -> Absent:
    return Absent("the settings screen is not answerable for this caller")


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _page(request: Request, saved: str) -> DestinationPage:
    records = records_of(request)
    secrets = secrets_of(request)
    every = await records.every()
    offers = await offered(every, secrets=secrets, transport=transport_of(request))
    chosen_channel = next((one for one in every if saved.startswith(f"{one.channel.value}:")), None)
    try:
        held = chosen_channel is not None and await asyncio.to_thread(
            secrets.held, chosen_channel.secret
        )
    except ChannelSecretsUnavailableError:
        held = False
    chosen, why = standing(saved, record=chosen_channel, secret_held=held)
    return DestinationPage(
        channel=None if chosen is None else chosen.channel.value,
        conversation=None if chosen is None else chosen.conversation,
        stopped_because=why,
        offers=tuple(
            ChannelOfferView(
                channel=offer.channel.value,
                conversations=tuple(
                    ConversationView(
                        channel=one.destination.channel.value,
                        conversation=one.destination.conversation,
                        name=one.name,
                    )
                    for one in offer.conversations
                ),
                why_none=offer.why_none,
            )
            for offer in offers
        ),
    )


@router.get(DESTINATION_PATH, response_model=DestinationPage, responses=COMMON_RESPONSES)
async def destination(request: Request, asked: Asked) -> DestinationPage:
    """Where the digest goes now, whether it can, and what every connected channel offers."""
    if not may_configure(asked.reach, asked.now):
        raise _not_answerable()
    return await _page(request, value_of(DESTINATION_SETTING))


@router.put(DESTINATION_PATH, response_model=DestinationPage, responses=COMMON_RESPONSES)
async def choose(request: Request, body: ChooseAsked, asked: Asked) -> DestinationPage:
    """Save a choice that is on the list now, or switch the digest off. Audited as the Settings
    screen's saves are. See `A_DESTINATION_IS_CHOSEN_FROM_WHAT_THE_CHANNEL_OFFERS`."""
    if not may_configure(asked.reach, asked.now):
        raise _not_answerable()
    if body.off:
        value = UNSET
    else:
        try:
            choice = Destination(Channel(body.channel), body.conversation)
        except ValueError as refused:
            raise Absent("that conversation is not offered by a connected channel") from refused
        offers = await offered(
            await records_of(request).every(),
            secrets=secrets_of(request),
            transport=transport_of(request),
        )
        if not is_offered(choice, offers):
            log.info(
                "digest destination refused",
                reason=A_DESTINATION_IS_CHOSEN_FROM_WHAT_THE_CHANNEL_OFFERS,
            )
            raise Absent("that conversation is not offered by a connected channel")
        value = choice.saved
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    async with sessions() as session:
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            await session.execute(statement)
        await save(session, {DESTINATION_SETTING: value}, updated_by=asked.caller.principal.id)
        saved = await load(session)
        await session.commit()
    hold_saved(saved)
    log.info("digest destination saved", principal=asked.caller.principal.id, off=body.off)
    return await _page(request, value)
