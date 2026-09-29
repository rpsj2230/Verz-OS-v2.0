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

**The module list is a listing of the channels this reader may manage, and nothing else.**
`GET /console/channels` is one row per channel an adapter declares and the reader holds the
channel's authority over, on `brain.listing`'s convention, so the console searches, filters and
orders it on the server; a channel outside the reader's authority is not a row, and one channel's
own row (`GET /console/channels/{name}`) is the same 404 for it as for a name that is no channel.
Each row carries the record's state, whether the secret is held, the health above, and who last
changed the record by name, so the page shows a person and keeps their id under Advanced. See
`A_CHANNEL_ROW_IS_THE_RECORD_THE_HEALTH_AND_A_NAME`.

**Each channel says the verbs it may carry and how it answers a group (M27.15.43).** The verbs
are `brain.gate.admission.CHANNEL_VERBS` for the channel, read rather than restated. Rooms are
read live from the vendor at question time and recorded nowhere, so there is no list of a
channel's rooms to show; what the screen can say truthfully is how a group is answered on it:
at the floor of everybody present on a wire that reads a room, as a floor of nothing on one that
cannot, and not at all on a channel this release does not receive. See `ROOMS_TOLD`.

Task ids: M10.3.1, M10.3.2, M10.3.4, M10.1.2, M10.1.3, M10.1.4, M27.13.1, M27.15.43
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Collection, Mapping
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
    events_address_of,
    events_path_of,
    may_manage,
    records_of,
    secrets_of,
    steps_of,
)
from brain.channels.adapter import adapter_for, channel_adapters, channel_wires
from brain.channels.binding import BindingCodes, BindingTable, mint_code
from brain.chat_answer import RoomReader
from brain.console.channel_health import ChannelHealthState, channel_health
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.gate.admission import CHANNEL_VERBS
from brain.gate.context import Channel
from brain.gate.ingress import NONCE_TTL, BindingRefusedError
from brain.guide_views import GuideStepView
from brain.identity.oidc import TokenRefusedError
from brain.identity.roles import IdentityError
from brain.identity.sessions import open_session
from brain.listing import Column, ListAsked, Listing
from brain.member.connections import my_channels
from brain.member.shell import member_screen
from brain.ops.binding_store import StoredBindings, StoredCodes
from brain.ops.channel_store import ChannelRecord, ChannelSecrets, ChannelSecretsUnavailableError
from brain.routing_routes import names_of, sessions_of

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

#: Why a module row carries the record's state, the health and a name.
A_CHANNEL_ROW_IS_THE_RECORD_THE_HEALTH_AND_A_NAME: Final = (
    "A channel's row is what its manager decides from: whether it is set up and switched on, "
    "whether its secret is held, how its deliveries say it is doing, and who changed it last, by "
    "name. The person's id travels beside the name for the Advanced section, and a channel the "
    "reader may not manage is no row at all, so the list has nothing to count."
)

CHANNEL_LIST_PATH: Final = "/console/channels"
CHANNEL_ROW_PATH: Final = CHANNEL_LIST_PATH + "/{name}"

#: What each channel is called on a screen. A product word, the same on every install.
CHANNEL_LABELS: Final[Mapping[Channel, str]] = {
    Channel.EMAIL: "Email",
    Channel.LARK: "Lark",
    Channel.SLACK: "Slack",
    Channel.TEAMS: "Microsoft Teams",
    Channel.TELEGRAM: "Telegram",
    Channel.WEBHOOK: "Webhook",
    Channel.WHATSAPP: "WhatsApp",
    Channel.WIDGET: "Website widget",
}


class RoomAnswer(enum.StrEnum):
    """How a group conversation is answered on one channel (M27.15.43)."""

    #: The wire reads who is present, so the room is answered at everybody's floor.
    AT_THE_FLOOR = "at_the_floor"
    #: The wire cannot read who is present, so the floor is taken as nothing.
    AS_NOTHING = "as_nothing"
    #: This release does not receive on the channel, so no group is answered on it.
    NOT_RECEIVED = "not_received"


#: What the screen says for each. `brain.chat_answer` is where each of them is decided.
ROOMS_TOLD: Final[Mapping[RoomAnswer, str]] = {
    RoomAnswer.AT_THE_FLOOR: (
        "In a group, who is present is read from the vendor when the question is asked. The room "
        "is answered at the floor of everybody in it, and the asker reads their own answer "
        "privately, or is sent a link."
    ),
    RoomAnswer.AS_NOTHING: (
        "This channel cannot say who is in a group, so a group's floor is taken as nothing: the "
        "room is told nothing, and the asker is answered privately, or sent a link."
    ),
    RoomAnswer.NOT_RECEIVED: (
        "This release does not receive on this channel, so no group is answered on it."
    ),
}


class ChannelStatus(enum.StrEnum):
    """Whether a channel's record exists and is switched on."""

    ON = "on"
    OFF = "off"
    NOT_SET_UP = "not_set_up"


class SecretState(enum.StrEnum):
    """Whether a channel's secret is held, in the four answers the vault can give."""

    HELD = "held"
    NOT_HELD = "not_held"
    #: The vault could not be asked, so whether it is held is not known.
    UNKNOWN = "unknown"
    #: The channel has no record, so no secret is kept for it.
    NONE = "none"


def channel_label(channel: Channel) -> str:
    """What a channel is called on a screen."""
    return CHANNEL_LABELS.get(channel, channel.value)


def rooms_for(channel: Channel) -> RoomAnswer:
    """How a group is answered on this channel, by what its wire can do. See `ROOMS_TOLD`."""
    # Typed as an object, as `brain.chat_answer` does: whether a wire reads a room is its class's.
    wire: object = channel_wires().get(channel)
    if wire is None:
        return RoomAnswer.NOT_RECEIVED
    return RoomAnswer.AT_THE_FLOOR if isinstance(wire, RoomReader) else RoomAnswer.AS_NOTHING


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
    #: What a person may do through it: `brain.gate.admission.CHANNEL_VERBS` (M27.15.43).
    verbs: list[str]
    #: How a group conversation is answered on it, and that in words.
    rooms: RoomAnswer
    rooms_told: str
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


class ChannelRowView(BaseModel):
    """One channel on the module list, and the head of its own page. Never its secret.

    See `A_CHANNEL_ROW_IS_THE_RECORD_THE_HEALTH_AND_A_NAME`. `last_delivered_at` is the newest
    message received or sent that went through, which is what "last active" means to a manager;
    a stranger's refused request is not activity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    label: str
    #: Whether this release can receive and reply on it.
    receives: bool
    status: ChannelStatus
    secret: SecretState
    health: ChannelHealthState
    last_delivered_at: datetime | None
    #: Where its vendor posts, under this install's origin; empty when it cannot receive.
    events_path: str
    #: The same address in full, to paste into the vendor; empty while the install names none.
    events_address: str
    #: The steps that connect it, ending in its own form; empty for a channel with none yet.
    steps: list[GuideStepView]
    tenant_fields: list[str]
    tenant: dict[str, str]
    changed_at: datetime | None
    changed_by: str | None
    changed_by_name: str | None


class ChannelListPage(BaseModel):
    """One page of the channels this reader may manage. Never a count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ChannelRowView]
    #: Present exactly when a further channel this reader may manage matches.
    next_cursor: str | None = None


#: What the module list may search, filter and order by: the fields a row shows.
CHANNEL_LIST: Final[Listing[ChannelRowView]] = Listing(
    name="channels",
    columns=(
        Column("label", lambda row: row.label, search=True, sort=True),
        Column("channel", lambda row: row.channel, search=True),
        Column("status", lambda row: row.status.value, filter=True, sort=True),
        Column("health", lambda row: row.health.value, filter=True),
        Column("receives", lambda row: row.receives, filter=True),
        Column("last_delivered_at", lambda row: row.last_delivered_at, sort=True),
    ),
    key=lambda row: row.channel,
    order="label",
)
ChannelListQuery = Annotated[ListAsked, Depends(CHANNEL_LIST.query())]


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


def _declared() -> list[Channel]:
    """Every channel an adapter declares, in the adapters' order."""
    return [factory().capabilities().channel for factory in channel_adapters()]


async def _names(request: Request, ids: Collection[str]) -> dict[str, str]:
    """The directory's names for these principals, or none on a process with no database."""
    sessions = sessions_of(request)
    if sessions is None or not ids:
        return {}
    async with sessions() as session:
        found = (await session.execute(names_of(ids))).all()
    return {str(pid): str(name) for pid, name in found}


async def _secret(record: ChannelRecord | None, secrets: ChannelSecrets) -> SecretState:
    """Whether the record's secret is held, from the slot's metadata. Never the secret."""
    if record is None:
        return SecretState.NONE
    try:
        held = await asyncio.to_thread(secrets.held, record.secret)
    except ChannelSecretsUnavailableError:
        return SecretState.UNKNOWN
    return SecretState.HELD if held else SecretState.NOT_HELD


async def _rows(request: Request, channels: list[Channel]) -> list[ChannelRowView]:
    """One row per channel named, which the caller has already decided the reader may manage.

    Deliveries are read only for a channel with a record, since a channel nobody set up is
    `not_set_up` whatever the table says, and names only for the people the records name.
    """
    if not channels:
        return []
    kept = {one.channel: one for one in await records_of(request).every()}
    records = {channel: kept.get(channel) for channel in channels}
    names = await _names(request, {one.updated_by for one in records.values() if one is not None})
    secrets = secrets_of(request)
    deliveries = deliveries_of(request)
    wires = channel_wires()
    rows: list[ChannelRowView] = []
    for channel, record in records.items():
        wire = wires.get(channel)
        found = channel_health(record, () if record is None else await deliveries.recent(channel))
        went = [one for one in (found.last_received_at, found.last_sent_at) if one is not None]
        rows.append(
            ChannelRowView(
                channel=channel.value,
                label=channel_label(channel),
                receives=wire is not None,
                status=(
                    ChannelStatus.NOT_SET_UP
                    if record is None
                    else ChannelStatus.ON
                    if record.enabled
                    else ChannelStatus.OFF
                ),
                secret=await _secret(record, secrets),
                health=found.health,
                last_delivered_at=max(went, default=None),
                events_path=events_path_of(channel),
                events_address=events_address_of(channel),
                steps=steps_of(channel),
                tenant_fields=list(wire.tenant_fields) if wire else [],
                tenant=dict(record.tenant) if record else {},
                changed_at=None if record is None else record.updated_at,
                changed_by=None if record is None else record.updated_by,
                changed_by_name=None if record is None else names.get(record.updated_by),
            )
        )
    return rows


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
        verbs=sorted(CHANNEL_VERBS.get(channel, frozenset())),
        rooms=rooms_for(channel),
        rooms_told=ROOMS_TOLD[rooms_for(channel)],
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


@router.get(CHANNEL_LIST_PATH, response_model=ChannelListPage, responses=COMMON_RESPONSES)
async def channel_list(request: Request, asked: Asked, listed: ChannelListQuery) -> ChannelListPage:
    """One page of the channels this reader may manage, searched, filtered and ordered.

    The authority is asked per channel before anything is read, so a channel outside it is
    neither a row nor a read, and the listing narrows only the rows the reader would be sent.
    """
    plan = CHANNEL_LIST.plan(listed, reader=asked.caller.principal.id)
    mine = [one for one in _declared() if may_manage(asked.reach, one, asked.now)]
    page = plan.page(await _rows(request, mine))
    return ChannelListPage(items=list(page.items), next_cursor=page.next_cursor)


@router.get(CHANNEL_ROW_PATH, response_model=ChannelRowView, responses=COMMON_RESPONSES)
async def channel_row(name: Name, request: Request, asked: Asked) -> ChannelRowView:
    """One channel's row, for its own page. Absent exactly as a name that is no channel."""
    channel = _managed(name, asked, receiving=False)
    (row,) = await _rows(request, [channel])
    return row
