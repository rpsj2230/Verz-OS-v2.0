"""Binding a chat account over HTTP, and what the Channels screen shows beyond a channel's record.

`brain.channel_routes` serves a channel's record, switch, test message and deliveries. This module
serves the rest of the Channels screen and the person's own half of binding: a code minted in My
workspace, the bindings a person or an administrator can take away, and each channel's declared
capabilities and its health read from its deliveries. It decides nothing that
`brain.channels.binding`, `brain.member.connections` or `brain.console.channel_health` decides.

**A code is minted only inside a live console sign-in, for the person signed in (M10.3.1).**
`brain.identity.sessions.open_session` builds the sign-in from the verified token, and refuses a
token with no session, which is what a service account's is; `brain.channels.binding.mint_code`
reads the person off it, so no request can name somebody else. The code is answered once, with
`Cache-Control: no-store`, and never logged; the store keeps its digest. See
`A_CODE_IS_SHOWN_ONCE_AND_KEPT_NOWHERE`.

**The person's routes open on the member screen `channels`, and every refusal is one 404.** The
member grant is what `brain.member.shell` gives everybody with an account, so a person holding
nothing administrative can bind their own chat, and `brain.console.reads.permitted` over that
screen's read decides it. A channel that is not switched on, one this release cannot receive on,
one the person holds nothing on and one that is no channel at all are one absence, so the route
cannot be walked to learn which channels an install runs beyond what the page already lists.

**An administrator's routes are the channel's own authority, the one `brain.channel_routes`
asks.** `brain.channel_routes.may_manage` over `<channel>_channel`, so whoever may switch a
channel on may see who is bound on it and unbind them, and a reader without it is answered as on a
channel that does not exist. See `A_CHANNEL_S_BINDINGS_ARE_GOVERNED_BY_THE_CHANNEL_S_AUTHORITY`.

**Unbinding is a POST, and it is recorded.** The console sends no DELETE, for
`console/src/api/client.ts`'s reason, and nothing here removes a row: the binding is retired in
`auth.principal_identity`, attributed to whoever pressed the control, and `0118`'s trigger appends
`channel_binding` unbound under the person.

**Health is the deliveries', not the adapter's (M10.1.4).** `brain.console.channel_health` reads
the newest deliveries into one of five states and ignores a stranger's refused request. The
capabilities an adapter declares, its features and the most sensitive class it may carry, are
served beside it as declared (M10.1.2, M10.1.3), so the screen says what a surface can do and
what it may never be sent.

Task ids: M10.3.1, M10.3.2, M10.3.4, M10.1.2, M10.1.3, M10.1.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from brain.api import API_PREFIX, COMMON_RESPONSES, NoEchoRoute
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.channel_routes import (
    DeliveryRowView,
    channel_named,
    deliveries_of,
    may_manage,
    records_of,
)
from brain.channels.adapter import adapter_for, channel_wires
from brain.channels.binding import BindingCodes, BindingTable, mint_code
from brain.console.channel_health import ChannelHealthState, channel_health
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.gate.context import Channel
from brain.gate.ingress import NONCE_TTL, BindingRefusedError
from brain.identity.oidc import TokenRefusedError
from brain.identity.roles import IdentityError
from brain.identity.sessions import open_session
from brain.listing import Column, ListAsked, Listing
from brain.member.connections import my_channels
from brain.member.shell import member_screen
from brain.ops.binding_store import StoredBindings, StoredCodes
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the code is answered once and kept nowhere.
A_CODE_IS_SHOWN_ONCE_AND_KEPT_NOWHERE: Final = (
    "A code is a credential for ten minutes. It is answered to the person who asked, marked not to "
    "be stored by anything between them and the server, never written to a log, and kept by the "
    "server only as a digest, so the one copy is the one on their screen."
)

#: Why a channel's bindings are governed by the channel's authority.
A_CHANNEL_S_BINDINGS_ARE_GOVERNED_BY_THE_CHANNEL_S_AUTHORITY: Final = (
    "Whoever may switch a channel on decides who it answers, so the same authority lists the "
    "people bound on it and takes a binding away. A reader without it is shown nothing about the "
    "channel's bindings and is refused as on a channel that does not exist."
)

# --------------------------------------------------------------------- the figures

MY_CHANNELS_PATH: Final = "/me/channels"
MY_CODE_PATH: Final = MY_CHANNELS_PATH + "/{name}/code"
MY_UNBIND_PATH: Final = MY_CHANNELS_PATH + "/{name}/unbind"
BINDINGS_PATH: Final = "/channels/{name}/bindings"
UNBIND_PATH: Final = BINDINGS_PATH + "/unbind"
HEALTH_PATH: Final = "/channels/{name}/health"

#: The member screen the person's routes open on. `brain.member.shell` registers it.
MEMBER_CHANNELS: Final = "channels"

#: The most bound people one listing reads. A page, and `truncated` says when it came back full.
MAX_BOUND_LISTED: Final = 500

MY_CHANNELS_TOLD: Final = (
    "To connect a chat account, ask for a code here and send it, on its own, to the Brain on that "
    "channel within ten minutes. A code works once, and asking for another ends the one before. "
    "Disconnecting stops the Brain answering that account as you."
)
BINDINGS_TOLD: Final = (
    "Each person listed proved a chat account is theirs by sending a code they asked for while "
    "signed in. Unbinding one stops the Brain answering that account as them, and is recorded in "
    "the audit ledger with your name."
)
UNBOUND_TOLD: Final = (
    "Unbound. The Brain no longer answers that account as them, and the audit ledger records it."
)


def code_told(channel: Channel) -> str:
    """What a person is told beside their code."""
    minutes = int(NONCE_TTL.total_seconds() // 60)
    return (
        f"Send this code, on its own, to the Brain on {channel.value} within {minutes} minutes. "
        "It works once. Ask for another if it lapses."
    )


# ------------------------------------------------------------------------ the shapes


class MyChannelView(BaseModel):
    """One chat channel on a person's own page. Never the account itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    bound: bool
    bound_at: datetime | None
    #: Whether a code may be asked for now.
    may_bind: bool


class MyChannelsView(BaseModel):
    """The person's chat channels, and how binding works."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channels: list[MyChannelView]
    told: str


class BindingCodeView(BaseModel):
    """A code, answered once. See `A_CODE_IS_SHOWN_ONCE_AND_KEPT_NOWHERE`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    code: str
    expires_at: datetime
    told: str


class BoundPersonView(BaseModel):
    """One person bound on a channel. Their name, never their account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    bound_at: datetime


class ChannelBindingsView(BaseModel):
    """One page of who is bound on one channel, by name. Never a count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    items: list[BoundPersonView]
    #: Present exactly when a further person this reader may see matches. See `brain.listing`.
    next_cursor: str | None = None
    #: Whether the load came back full, so more people are bound than any page can show.
    truncated: bool
    told: str


class ChannelUnboundView(BaseModel):
    """Whose binding was taken away, and what that did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    told: str


class UnbindAsked(BaseModel):
    """Whose binding on this channel to take away."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)


class ChannelHealthView(BaseModel):
    """A channel's declared capabilities, and its health read from its deliveries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    #: Whether this release can receive and reply on it.
    receives: bool
    #: What the adapter declares it can do: ephemeral, cards, streaming, attachments and more.
    features: list[str]
    #: The most sensitive classification it may ever be sent.
    max_classification: str
    #: Whether it can show a person the label an unchecked payload carries.
    can_carry_label: bool
    health: ChannelHealthState
    told: str
    last_received_at: datetime | None
    last_sent_at: datetime | None
    #: The newest delivery that failed for a fault, without anything it said.
    last_fault: DeliveryRowView | None


# ------------------------------------------------------------------------ the listing

#: What the bound people on a channel may be searched, filtered and ordered by: what a row shows.
BOUND: Final[Listing[BoundPersonView]] = Listing(
    name="channel-bindings",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("principal_id", lambda row: row.principal_id, search=True, filter=True),
        Column("bound_at", lambda row: row.bound_at, sort=True),
    ),
    key=lambda row: row.principal_id,
    order="display_name",
)
BoundQuery = Annotated[ListAsked, Depends(BOUND.query())]


# ------------------------------------------------------------------------ the wiring


def binding_codes_of(request: Request) -> BindingCodes:
    """`app.state.binding_codes` when a test put one there, `auth.binding_code` otherwise."""
    found: BindingCodes | None = getattr(request.app.state, "binding_codes", None)
    if found is not None:
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredCodes(sessions)


def table_of(request: Request) -> BindingTable:
    """`app.state.binding_table` when a test put one there, `auth.principal_identity` otherwise."""
    found: BindingTable | None = getattr(request.app.state, "binding_table", None)
    if found is not None:
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredBindings(sessions)


# ------------------------------------------------------------------------ the decisions


def _absent() -> Absent:
    return Absent("no channel here for this caller")


def _member(asked: Asking) -> str:
    """The person asking, when the member screen `channels` opens for them; one absence if not."""
    if not permitted(member_screen(MEMBER_CHANNELS).read, asked.reach, asked.now):
        raise _absent()
    return asked.caller.principal.id


def _chat(name: str) -> Channel:
    """A channel that is a chat: any channel an adapter declares, and never the console."""
    channel = channel_named(name)
    if channel is None or channel is Channel.CONSOLE:
        raise _absent()
    return channel


def _managed(name: str, asked: Asking, *, receiving: bool) -> Channel:
    """A channel this reader may manage, received by this release when asked; else absent."""
    channel = channel_named(name)
    if (
        channel is None
        or (receiving and channel not in channel_wires())
        or not may_manage(asked.reach, channel, asked.now)
    ):
        raise _absent()
    return channel


async def _offered(request: Request) -> frozenset[Channel]:
    """The channels a code may be asked for: received by this release and switched on."""
    wires = channel_wires()
    return frozenset(
        one.channel
        for one in await records_of(request).every()
        if one.enabled and one.channel in wires
    )


async def _my_view(request: Request, me: str) -> MyChannelsView:
    rows = my_channels(me, await table_of(request).for_principal(me), await _offered(request))
    return MyChannelsView(
        channels=[
            MyChannelView(
                channel=one.channel.value,
                bound=one.bound_at is not None,
                bound_at=one.bound_at,
                may_bind=one.may_bind,
            )
            for one in rows
        ],
        told=MY_CHANNELS_TOLD,
    )


# ------------------------------------------------------------------------ the routes

router = APIRouter(prefix=API_PREFIX, tags=["channels"], route_class=NoEchoRoute)

Name = Annotated[str, Path(max_length=32)]


@router.get(MY_CHANNELS_PATH, response_model=MyChannelsView, responses=COMMON_RESPONSES)
async def my_channel_list(request: Request, asked: Asked) -> MyChannelsView:
    """The asker's own chat channels: the ones they may bind and the ones they are bound on."""
    return await _my_view(request, _member(asked))


@router.post(MY_CODE_PATH, response_model=BindingCodeView, responses=COMMON_RESPONSES)
async def my_code(
    name: Name, request: Request, response: Response, asked: Asked
) -> BindingCodeView:
    """Mint a one-time code for this channel, in the asker's live sign-in, shown once."""
    _member(asked)
    channel = _chat(name)
    if channel not in await _offered(request) or asked.caller.service_account is not None:
        raise _absent()
    try:
        session = open_session(
            claims=asked.caller.claims, principal=asked.caller.principal, now=asked.now
        )
        minted = await mint_code(session, channel, now=asked.now, codes=binding_codes_of(request))
    except (TokenRefusedError, IdentityError, ValidationError, BindingRefusedError) as refused:
        log.info("channel code not minted", channel=channel.value, why=type(refused).__name__)
        raise _absent() from None
    response.headers["Cache-Control"] = "no-store"
    log.info("channel code minted", channel=channel.value, principal=minted.nonce.principal_id)
    return BindingCodeView(
        channel=channel.value,
        code=minted.nonce.value,
        expires_at=minted.nonce.minted_at + NONCE_TTL,
        told=code_told(channel),
    )


@router.post(MY_UNBIND_PATH, response_model=MyChannelsView, responses=COMMON_RESPONSES)
async def my_unbind(name: Name, request: Request, asked: Asked) -> MyChannelsView:
    """Take away the asker's own binding on this channel, recorded as theirs."""
    me = _member(asked)
    channel = _chat(name)
    retired = await table_of(request).unbind(
        me,
        channel,
        actor=me,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    if not retired:
        raise _absent()
    log.info("channel unbound by its person", channel=channel.value, principal=me)
    return await _my_view(request, me)


@router.get(BINDINGS_PATH, response_model=ChannelBindingsView, responses=COMMON_RESPONSES)
async def bindings(
    name: Name, request: Request, asked: Asked, listed: BoundQuery
) -> ChannelBindingsView:
    """One page of who is bound on this channel, for whoever may manage it.

    The channel's question first and the listing's second, so a reader without the authority is
    refused the same whatever they asked for, and the load is the same whatever was searched, for
    `brain.listing.THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.
    """
    channel = _managed(name, asked, receiving=True)
    plan = BOUND.plan(listed, reader=asked.caller.principal.id)
    people, truncated = await table_of(request).on_channel(channel, limit=MAX_BOUND_LISTED)
    page = plan.page(
        [
            BoundPersonView(
                principal_id=one.principal_id, display_name=one.display_name, bound_at=one.bound_at
            )
            for one in people
        ]
    )
    return ChannelBindingsView(
        channel=channel.value,
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=truncated,
        told=BINDINGS_TOLD,
    )


@router.post(UNBIND_PATH, response_model=ChannelUnboundView, responses=COMMON_RESPONSES)
async def unbind_someone(
    name: Name, body: UnbindAsked, request: Request, asked: Asked
) -> ChannelUnboundView:
    """Take away one person's binding on this channel, recorded as the administrator's act."""
    channel = _managed(name, asked, receiving=True)
    actor = asked.caller.principal.id
    retired = await table_of(request).unbind(
        body.principal_id,
        channel,
        actor=actor,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    if not retired:
        raise _absent()
    log.info("channel unbound", channel=channel.value, principal=body.principal_id, actor=actor)
    return ChannelUnboundView(principal_id=body.principal_id, told=UNBOUND_TOLD)


@router.get(HEALTH_PATH, response_model=ChannelHealthView, responses=COMMON_RESPONSES)
async def health(name: Name, request: Request, asked: Asked) -> ChannelHealthView:
    """This channel's declared capabilities and its health from its deliveries."""
    channel = _managed(name, asked, receiving=False)
    declared = adapter_for(channel).capabilities()
    record = await records_of(request).get(channel)
    found = channel_health(record, await deliveries_of(request).recent(channel))
    fault = found.last_fault
    return ChannelHealthView(
        channel=channel.value,
        receives=channel in channel_wires(),
        features=sorted(one.value for one in declared.features),
        max_classification=declared.max_classification.value,
        can_carry_label=declared.can_carry_label,
        health=found.health,
        told=found.told,
        last_received_at=found.last_received_at,
        last_sent_at=found.last_sent_at,
        last_fault=None
        if fault is None
        else DeliveryRowView(
            direction=fault.entry.direction,
            outcome=fault.entry.outcome,
            reason=fault.entry.reason,
            vendor_status=fault.entry.vendor_status,
            recorded_at=fault.recorded_at,
        ),
    )
