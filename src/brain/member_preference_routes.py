"""A member's own settings: whether they are learnt from, where they are reached, and when not.

One read and three writes, all for the person asking and taking no parameter naming a person, each
gated on the member grant (`brain.member.shell`), so DENIED and ABSENT are the page's one refusal.
Stored in `auth.member_preference` (`0228`) through `brain.ops.member_preference_store`, which can
only write as the person the transaction names.

**What a setting is allowed to say is checked where it is set, against what is true now.** A primary
channel and any channel with a notice choice must be one the person is bound on, because a primary
nobody proved is a default that fails on the first message (`brain.member.connections.reachability`
argues it); an approval is routed only to the console or to a Lark card, and a Lark card only where
they are bound on Lark; two quiet-hour times that are equal are refused because they read as both
"none" and "all day". Each refusal is in words and names the setting, never anybody else.

**Learning is switched off with its cost said, and nothing is removed.** `member_activity.opt_out`
is the one statement of what stops and what stays, and its cost sentence is what the page shows
beside the switch, so a person is not told it is off when tier zero still remembers a conversation
within itself. Removing what has been learnt is `forget-all` or a deletion request, which are other
requests with other routes.

**Quiet hours cover digests and automation notices, and the page says an approval is never held**,
which is `brain.member.connections.AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING` carried to
the screen so the setting is not read as a promise about everything.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked
from brain.binding_routes import table_of
from brain.channels.binding import BindingTable
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.gate.context import Channel
from brain.member.connections import (
    AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING,
    QUIET_HOURS_APPLY_TO,
    ChannelPreference,
    NotificationKind,
    channels_that_may_approve,
    reachable_on,
)
from brain.member.preferences import (
    APPROVAL_ROUTES,
    PreferenceKey,
    Preferences,
    clock,
    notices_value,
)
from brain.member.shell import member_screen
from brain.member_activity import opt_out
from brain.mine_routes import MEMBER_HOME
from brain.ops.member_preference_store import StoredPreferences
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

#: What a refused setting returns beside the one 404: a sentence about the setting asked for.
PREFERENCE_RESPONSES: Final = {
    **COMMON_RESPONSES,
    422: {"model": ErrorBody, "description": "That setting cannot be kept, and why, in words."},
}

#: The kinds a person may choose for a channel: what quiet hours cover. An approval is never a
#: choice, because it expires and is never held back.
CHOOSABLE_KINDS: Final[tuple[str, ...]] = tuple(sorted(one.value for one in QUIET_HOURS_APPLY_TO))

Clock = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


def _not_answerable() -> Absent:
    return Absent("your settings are not answerable for this caller")


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own settings not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


def _refused(field: str, message: str) -> JSONResponse:
    told = ErrorBody(
        message=message,
        problems=[RequestProblemView(field=field, code="not_keepable", message=message)],
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _store(request: Request) -> StoredPreferences:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredPreferences(sessions)


# ------------------------------------------------------------------------------ shapes
class LearningView(BaseModel):
    """Whether personal learning is off for this person, and what switching it off costs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opted_out: bool
    cost: str


class ChannelSettingView(BaseModel):
    """One channel this person is bound on, whether it is primary, and what they asked of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    primary: bool
    #: Whether this person made any statement about what this channel tells them.
    chosen: bool
    notify: list[str]
    may_carry_an_approval: bool


class QuietView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: str
    end: str


class PreferencesView(BaseModel):
    """This person's settings, and the choices open to them. Nothing about anybody else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    learning: LearningView
    channels: list[ChannelSettingView]
    primary: str | None
    #: `None` is wherever an approval may be carried.
    approval_route: str | None
    approval_choices: list[str]
    notice_kinds: list[str]
    quiet: QuietView | None
    quiet_applies_to: list[str]
    approvals_are_never_held: str
    #: Settings stored and not understood, by name, so the page can say they are not in force.
    ignored: list[str]


class LearningAsked(BaseModel):
    """Whether this person is switching personal learning off (true) or back on (false)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opted_out: bool


class ChannelNotices(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    notify: list[str]


class ReachAsked(BaseModel):
    """Where this person is reached: the primary, what each channel may tell them, and where an
    approval waits. Sent whole, because a half-saved reach is two settings that disagree."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primary: str | None = None
    notices: list[ChannelNotices] = []
    approval_route: str | None = None


class QuietAsked(BaseModel):
    """Two wall-clock times, or neither to clear them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: Clock | None = None
    end: Clock | None = None


# ----------------------------------------------------------------------- the decisions
def view_of(settings: Preferences, bound: tuple[Channel, ...]) -> PreferencesView:
    """The page for these settings and the channels this person is bound on right now."""
    channels = [
        ChannelSettingView(
            channel=one.value,
            primary=settings.primary is one,
            chosen=settings.says(one),
            notify=sorted(
                kind.value
                for preference in settings.notices
                if preference.channel is one
                for kind in preference.notify
            ),
            may_carry_an_approval=bool(channels_that_may_approve((one,))),
        )
        for one in bound
    ]
    choices = [Channel.CONSOLE.value] + [
        one.value for one in channels_that_may_approve(bound) if one in APPROVAL_ROUTES
    ]
    return PreferencesView(
        learning=LearningView(
            opted_out=settings.learning_opted_out,
            cost=opt_out(principal_id=settings.principal_id or "-", at=datetime.now(UTC)).cost,
        ),
        channels=channels,
        primary=None if settings.primary is None else settings.primary.value,
        approval_route=None if settings.approval_route is None else settings.approval_route.value,
        approval_choices=choices,
        notice_kinds=list(CHOOSABLE_KINDS),
        quiet=None
        if settings.quiet is None
        else QuietView(start=clock(settings.quiet.start), end=clock(settings.quiet.end)),
        quiet_applies_to=list(CHOOSABLE_KINDS),
        approvals_are_never_held=AN_APPROVAL_HELD_UNTIL_MORNING_HAS_EXPIRED_BY_MORNING,
        ignored=sorted(settings.ignored),
    )


async def _bound(request: Request, principal_id: str) -> tuple[Channel, ...]:
    table: BindingTable = table_of(request)
    return reachable_on(principal_id, await table.for_principal(principal_id))


async def _page(request: Request, asked: Asked) -> PreferencesView:
    me = asked.caller.principal.id
    return view_of(await _store(request).of(me), await _bound(request, me))


def _channel(value: str) -> Channel | None:
    try:
        return Channel(value)
    except ValueError:
        return None


# ------------------------------------------------------------------------------ routes
@router.get("/me/preferences", response_model=PreferencesView, responses=COMMON_RESPONSES)
async def my_preferences(request: Request, asked: Asked) -> PreferencesView:
    """This person's settings and where they may be reached (M40.5.2.1, M40.4.1.4)."""
    _guard(asked)
    return await _page(request, asked)


@router.post(
    "/me/preferences/learning", response_model=PreferencesView, responses=PREFERENCE_RESPONSES
)
async def set_learning(request: Request, body: LearningAsked, asked: Asked) -> PreferencesView:
    """Switch personal learning off or on (M40.4.1.4). Removes nothing already learnt."""
    _guard(asked)
    me = asked.caller.principal.id
    store = _store(request)
    if body.opted_out:
        await store.set(me, PreferenceKey.LEARNING_OPT_OUT, {"on": True}, now=asked.now)
    else:
        await store.clear(me, PreferenceKey.LEARNING_OPT_OUT)
    log.info("own learning set", principal=me, opted_out=body.opted_out)
    return await _page(request, asked)


@router.post(
    "/me/preferences/reach", response_model=PreferencesView, responses=PREFERENCE_RESPONSES
)
async def set_reach(
    request: Request, body: ReachAsked, asked: Asked
) -> PreferencesView | JSONResponse:
    """Keep where this person is reached, whole, or refuse it in words (M40.5.2.1 to M40.5.2.3)."""
    _guard(asked)
    me = asked.caller.principal.id
    bound = await _bound(request, me)

    primary: Channel | None = None
    if body.primary is not None:
        primary = _channel(body.primary)
        if primary is None or primary not in bound:
            return _refused("primary", f"{body.primary} is not a channel you are connected on.")
    choices: list[ChannelPreference] = []
    seen: set[Channel] = set()
    for one in body.notices:
        channel = _channel(one.channel)
        if channel is None or channel not in bound:
            return _refused("notices", f"{one.channel} is not a channel you are connected on.")
        if channel in seen:
            return _refused("notices", f"{one.channel} is chosen twice.")
        seen.add(channel)
        try:
            kinds = frozenset(NotificationKind(kind) for kind in one.notify)
        except ValueError:
            return _refused("notices", "That is not a kind of message you can choose.")
        if not kinds <= QUIET_HOURS_APPLY_TO:
            return _refused("notices", "An approval is not a choice: it is always sent.")
        choices.append(ChannelPreference(channel=channel, notify=kinds))
    route: Channel | None = None
    if body.approval_route is not None:
        route = _channel(body.approval_route)
        allowed = {Channel.CONSOLE, *(one for one in channels_that_may_approve(bound))}
        if route not in APPROVAL_ROUTES or route not in allowed:
            return _refused(
                "approval_route",
                "An approval can wait on the console, or on a Lark card where you are connected "
                "on Lark, and nowhere else.",
            )

    store = _store(request)
    for key, value in (
        (PreferenceKey.PRIMARY_CHANNEL, None if primary is None else {"channel": primary.value}),
        (PreferenceKey.CHANNEL_NOTICES, notices_value(choices) if choices else None),
        (PreferenceKey.APPROVAL_ROUTE, None if route is None else {"channel": route.value}),
    ):
        if value is None:
            await store.clear(me, key)
        else:
            await store.set(me, key, value, now=asked.now)
    log.info("own reach set", principal=me)
    return await _page(request, asked)


@router.post(
    "/me/preferences/quiet-hours", response_model=PreferencesView, responses=PREFERENCE_RESPONSES
)
async def set_quiet_hours(
    request: Request, body: QuietAsked, asked: Asked
) -> PreferencesView | JSONResponse:
    """Hold digests and automation notices between two times, or clear it (M40.5.2.4)."""
    _guard(asked)
    me = asked.caller.principal.id
    store = _store(request)
    if body.start is None and body.end is None:
        await store.clear(me, PreferenceKey.QUIET_HOURS)
        return await _page(request, asked)
    if body.start is None or body.end is None:
        return _refused("quiet_hours", "Quiet hours need a start and an end, or neither.")
    if body.start == body.end:
        return _refused(
            "quiet_hours",
            "The start and the end are the same time, which reads as both none and all day.",
        )
    await store.set(
        me, PreferenceKey.QUIET_HOURS, {"start": body.start, "end": body.end}, now=asked.now
    )
    return await _page(request, asked)
