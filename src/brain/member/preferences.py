"""What a person keeps about how they are reached and what is learnt from them, as values.

Five settings, each a JSON document under one key in `auth.member_preference` (`0229`), and this
module is the one place that says what each looks like: **a value is parsed here and never read as
a raw dictionary elsewhere**, so a row written by an older release, or by hand, is ignored in the
safe direction rather than half understood.

**Every default is the quiet or the unchanged one.** No row for a key means learning on, no primary
channel, a channel that wants nothing extra (`brain.member.connections.wants` says an absent
preference wants nothing), approvals offered everywhere they may be carried, and no quiet hours.
Reading a stale or malformed value gives the default and never an error, because a sender that
raised on one person's bad row would stop every message after theirs.

**An approval is routed only between the console and a Lark card**, which is the leaf's own list
(M40.5.2.3). `brain.member.connections.channels_that_may_approve` decides which channels may carry
an approve at all and is asked here, so a channel whose ceiling changes changes this at the same
moment; what this adds is the narrower list the leaf names, and the console, which is not a chat
binding.

Rejected: reading the five settings through `brain.member.connections.reachability`. It refuses a
primary channel with no binding and an approval route with no binding, which is right at the moment
a person sets one and wrong at the moment a sender reads one, when the binding may have been taken
away since: a stale preference is to be ignored, not to fail the digest.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import time
from types import MappingProxyType
from typing import Any, Final

from brain.gate.context import Channel
from brain.member.connections import (
    ChannelPreference,
    NotificationKind,
    QuietHours,
    channels_that_may_approve,
)


class PreferenceKey(enum.StrEnum):
    """The five settings, held equal to `0229`'s list by a test."""

    APPROVAL_ROUTE = "approval_route"
    CHANNEL_NOTICES = "channel_notices"
    LEARNING_OPT_OUT = "learning_opt_out"
    PRIMARY_CHANNEL = "primary_channel"
    QUIET_HOURS = "quiet_hours"


#: Where an envelope waiting for a person may be put in front of them, and nowhere else.
APPROVAL_ROUTES: Final[tuple[Channel, ...]] = (Channel.CONSOLE, Channel.LARK)

#: What a setting that was never made says, in the words a person reads.
NEVER_SET: Final = "Not set."


@dataclass(frozen=True)
class Preferences:
    """One person's settings, parsed. Every field has the quiet default."""

    principal_id: str
    learning_opted_out: bool = False
    primary: Channel | None = None
    notices: tuple[ChannelPreference, ...] = ()
    #: None is every place an approval may be carried, which is what happened before this existed.
    approval_route: Channel | None = None
    quiet: QuietHours | None = None
    #: What a stored value was ignored for, by key, so a screen can say so rather than show a
    #: setting the person did not make.
    ignored: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def wants(self, channel: Channel, kind: NotificationKind) -> bool:
        """Whether this person asked for this kind of message on this channel.

        A channel they said nothing about wants nothing extra: that is `connections.wants` for an
        absent preference. Callers decide what nothing extra means for a message they must send.
        """
        for one in self.notices:
            if one.channel is channel:
                return kind in one.notify
        return False

    def says(self, channel: Channel) -> bool:
        """Whether this person made any statement about this channel's notices."""
        return any(one.channel is channel for one in self.notices)

    def lets_an_approval_go_to(self, channel: Channel) -> bool:
        """Whether an approval may be put in front of them on `channel`.

        True for every channel that may carry one when they chose none, and only for the one they
        chose otherwise. A channel that may not carry an approve is never true.
        """
        if channel not in channels_that_may_approve((channel,)):
            return False
        return self.approval_route is None or self.approval_route is channel


def _channel(value: object) -> Channel | None:
    try:
        return Channel(str(value))
    except ValueError:
        return None


def _kinds(values: object) -> frozenset[NotificationKind] | None:
    if not isinstance(values, list):
        return None
    found: set[NotificationKind] = set()
    for one in values:
        try:
            kind = NotificationKind(str(one))
        except ValueError:
            return None
        found.add(kind)
    return frozenset(found)


def _minute(text: object) -> time | None:
    if not isinstance(text, str) or len(text) != 5 or text[2] != ":":
        return None
    try:
        return time(int(text[:2]), int(text[3:]))
    except ValueError:
        return None


def clock(at: time) -> str:
    """A wall-clock time as the person typed it, `HH:MM`."""
    return f"{at.hour:02d}:{at.minute:02d}"


def parse(principal_id: str, stored: Mapping[str, Any]) -> Preferences:
    """The settings a person has, from the rows stored for them, ignoring what does not parse."""
    ignored: dict[str, str] = {}
    opted_out = False
    primary: Channel | None = None
    notices: list[ChannelPreference] = []
    route: Channel | None = None
    quiet: QuietHours | None = None

    one = stored.get(PreferenceKey.LEARNING_OPT_OUT.value)
    if one is not None:
        if isinstance(one, dict) and isinstance(one.get("on"), bool):
            opted_out = bool(one["on"])
        else:
            ignored[PreferenceKey.LEARNING_OPT_OUT.value] = "not a switch"
    one = stored.get(PreferenceKey.PRIMARY_CHANNEL.value)
    if one is not None:
        primary = _channel(one.get("channel")) if isinstance(one, dict) else None
        if primary is None:
            ignored[PreferenceKey.PRIMARY_CHANNEL.value] = "not a channel"
    one = stored.get(PreferenceKey.CHANNEL_NOTICES.value)
    if one is not None:
        parsed: list[ChannelPreference] = []
        good = isinstance(one, dict)
        for name, kinds in one.items() if isinstance(one, dict) else ():
            channel, wanted = _channel(name), _kinds(kinds)
            if channel is None or wanted is None:
                good = False
                break
            parsed.append(ChannelPreference(channel=channel, notify=wanted))
        if good:
            notices = sorted(parsed, key=lambda item: item.channel.value)
        else:
            ignored[PreferenceKey.CHANNEL_NOTICES.value] = "not channels and kinds"
    one = stored.get(PreferenceKey.APPROVAL_ROUTE.value)
    if one is not None:
        route = _channel(one.get("channel")) if isinstance(one, dict) else None
        if route not in APPROVAL_ROUTES:
            route = None
            ignored[PreferenceKey.APPROVAL_ROUTE.value] = "not the console or a Lark card"
    one = stored.get(PreferenceKey.QUIET_HOURS.value)
    if one is not None:
        start = _minute(one.get("start")) if isinstance(one, dict) else None
        end = _minute(one.get("end")) if isinstance(one, dict) else None
        if start is not None and end is not None and start != end:
            quiet = QuietHours(start=start, end=end)
        else:
            ignored[PreferenceKey.QUIET_HOURS.value] = "not two different times"
    return Preferences(
        principal_id=principal_id,
        learning_opted_out=opted_out,
        primary=primary,
        notices=tuple(notices),
        approval_route=route,
        quiet=quiet,
        ignored=MappingProxyType(ignored),
    )


def notices_value(choices: Iterable[ChannelPreference]) -> dict[str, list[str]]:
    """The document stored for a person's channel notices, sorted so equal choices store equal."""
    return {
        one.channel.value: sorted(kind.value for kind in one.notify)
        for one in sorted(choices, key=lambda item: item.channel.value)
    }
