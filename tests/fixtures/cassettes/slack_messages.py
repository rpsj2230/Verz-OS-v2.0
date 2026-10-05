"""Slack's recordings: the channels and members the worker indexes, a member's channels and a
channel's history read for one question, and the failures Slack answers with.

A channel's topic and purpose, a member's name and phone, and a message's text carry canaries:
none of them is kept. A member's email is digested and the address itself is kept nowhere, which
`tests/unit/test_slack_messages.py` asserts on the raw address rather than on a canary, because a
canary in place of an address is not an address and the member would not be kept at all.

Task ids: M11.7.5
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from brain.connectors import slack_messages as slack
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.idempotency import Verification
from tests.fixtures.cassettes._read_back import answered
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "slack_messages"

SLACK_DOC = "https://docs.slack.dev/reference/methods/"
RATE_DOC = "https://docs.slack.dev/apis/web-api/rate-limits"

#: The workspace's ids the recordings name, shaped as Slack's are and naming nobody.
PUBLIC_CHANNEL: Final = "C0123PUBLIC"
PRIVATE_CHANNEL: Final = "G0123PRIVATE"
UNINVITED_CHANNEL: Final = "C0123NOTIN"
MEMBER: Final = "U0123MEMBER"
#: The member's confirmed work address, which is digested and never kept.
MEMBER_EMAIL: Final = "someone@workspace.example"


def _channel(ident: str, name: str, *, private: bool, member: bool) -> dict[str, Any]:
    return {
        "id": ident,
        "name": name,
        "is_channel": not private,
        "is_group": private,
        "is_private": private,
        "is_archived": False,
        "is_member": member,
        "created": 1_600_000_000,
        "topic": {"value": "CANARY-SLACK-TOPIC", "creator": MEMBER, "last_set": 0},
        "purpose": {"value": "CANARY-SLACK-PURPOSE", "creator": MEMBER, "last_set": 0},
        "num_members": 12,
    }


def _member(
    ident: str, email: str, *, confirmed: bool = True, bot: bool = False, deleted: bool = False
) -> dict[str, Any]:
    return {
        "id": ident,
        "team_id": "T0123ABCD",
        "name": "someone",
        "deleted": deleted,
        "real_name": "CANARY-SLACK-REAL-NAME",
        "is_bot": bot,
        "is_email_confirmed": confirmed,
        "profile": {
            "real_name": "CANARY-SLACK-PROFILE-NAME",
            "display_name": "CANARY-SLACK-DISPLAY-NAME",
            "phone": "CANARY-SLACK-PHONE",
            "email": email,
        },
    }


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="SLACK-200-channels",
        source=SOURCE,
        request=(
            "GET /api/conversations.list?limit=200&types=public_channel,private_channel"
            "&exclude_archived=true"
        ),
        status=200,
        body={
            "ok": True,
            "channels": [
                _channel(PUBLIC_CHANNEL, "pricing", private=False, member=True),
                _channel(PRIVATE_CHANNEL, "leadership", private=True, member=True),
                _channel(UNINVITED_CHANNEL, "random", private=False, member=False),
            ],
            "response_metadata": {"next_cursor": ""},
        },
        why="The channels the index reads. A public channel is listed whether or not the app "
        "was invited, so is_member is what says the app may read it; a private one is listed "
        "only once the app is in it. An empty next_cursor is the end. Topic and purpose are "
        "canaries: a channel is kept by its name and whether it is private, and nothing else.",
        kind=Kind.LIST,
        projects=slack.CHANNEL,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "conversations.list",
    ),
    Cassette(
        cid="SLACK-200-members",
        source=SOURCE,
        request="GET /api/users.list?limit=200",
        status=200,
        body={
            "ok": True,
            "members": [
                _member(MEMBER, MEMBER_EMAIL),
                _member("U0123UNCONF", "unconfirmed@workspace.example", confirmed=False),
                _member("U0123GONE", "gone@workspace.example", deleted=True),
                _member("B0123BOT", "bot@workspace.example", bot=True),
            ],
            "response_metadata": {"next_cursor": "dXNlcjpVMEc5V0ZYTlo="},
        },
        why="A page of members with another behind it: a non-empty next_cursor is the only "
        "sign. A member is kept only with a confirmed address, as its digest, and a deleted "
        "member and a bot are not kept. The names and the phone are canaries.",
        kind=Kind.PAGINATION,
        projects=slack.MEMBER,
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "users.list",
    ),
    Cassette(
        cid="SLACK-200-membership",
        source=SOURCE,
        request=(
            f"GET /api/users.conversations?user={MEMBER}&types=public_channel,private_channel"
            "&exclude_archived=true&limit=200"
        ),
        status=200,
        body={
            "ok": True,
            "channels": [_channel(PUBLIC_CHANNEL, "pricing", private=False, member=True)],
            "response_metadata": {"next_cursor": ""},
        },
        why="The channels one member is in, of those the app can see, asked of Slack for the "
        "question and never kept. The private channel is absent because this member is not in "
        "it, which is the whole of how a private channel is kept from them.",
        kind=Kind.LIST,
        tools=("slack_messages.find_messages",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "users.conversations",
    ),
    Cassette(
        cid="SLACK-200-history",
        source=SOURCE,
        request=f"GET /api/conversations.history?channel={PUBLIC_CHANNEL}&limit=100",
        status=200,
        body={
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "user": MEMBER,
                    "text": "CANARY-SLACK-MESSAGE-TEXT",
                    "ts": "1600000100.000200",
                },
                {
                    "type": "message",
                    "user": MEMBER,
                    "text": "The retainer price is agreed at the new rate.",
                    "ts": "1600000000.000100",
                },
            ],
            "has_more": False,
            "response_metadata": {"next_cursor": ""},
        },
        why="A channel's recent messages, newest first, read for one question and never kept. "
        "The text is a canary.",
        kind=Kind.READ,
        tools=("slack_messages.find_messages",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "conversations.history",
    ),
    Cassette(
        cid="SLACK-200-not-ok",
        source=SOURCE,
        request="GET /api/conversations.list?limit=200",
        status=200,
        body={"ok": False, "error": "invalid_auth"},
        why="Slack answers most refusals with HTTP 200 and ok false: a revoked token, a missing "
        "scope, a channel the app is not in. A connector reading the status alone would read "
        "this as a workspace with no channels.",
        kind=Kind.ERROR,
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "conversations.list",
    ),
    Cassette(
        cid="SLACK-429",
        source=SOURCE,
        request="GET /api/users.list?limit=200",
        status=429,
        headers={"Retry-After": "30"},
        body={"ok": False, "error": "ratelimited"},
        why="Slack's own 429, with the wait in seconds in Retry-After, per method and per "
        "workspace.",
        kind=Kind.RATE_LIMIT,
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=RATE_DOC,
    ),
    Cassette(
        cid="SLACK-503",
        source=SOURCE,
        request=f"GET /api/conversations.history?channel={PUBLIC_CHANNEL}&limit=100",
        status=503,
        body={"ok": False, "error": "service_unavailable"},
        why="Slack is down or degraded. Not a refusal and not an empty channel: the question is "
        "answered without Slack and nothing is concluded about what it holds.",
        kind=Kind.ERROR,
        tools=("slack_messages.find_messages",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=SLACK_DOC + "conversations.history",
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    20,
    "calls a minute per method per workspace, at Tier 2",
    "conversations.list and users.list are Tier 2, 20 or more a minute; users.conversations "
    "and conversations.history are Tier 3, 50 or more. Slack sets the tier and no plan moves it.",
    False,
)


def operation_of(recorded: Cassette) -> Any:
    """The operation a recording's request was made with."""
    if "/users.conversations" in recorded.request:
        return slack.membership_operation()
    if "/conversations.history" in recorded.request:
        return slack.history_operation()
    if "/users.list" in recorded.request:
        return slack.operation_for(slack.MEMBER)
    return slack.operation_for(slack.CHANNEL)


def replay(recorded: Cassette) -> Replayed:
    """A recording through the reading's own interpreter, its projection and its paging."""
    call = classify(status=recorded.status)
    if call is CallOutcome.REJECTED:
        return Replayed(Expect.REFUSED)
    if call is not CallOutcome.OK:
        return Replayed(unreachable_or_quota(call))
    try:
        slack.answered(recorded.body)
    except slack.SlackError:
        return Replayed(Expect.REFUSED)
    rows = operation_of(recorded).project(recorded.body)
    if not rows:
        return Replayed(Expect.ABSENT)
    reading = slack.SlackReading()
    kept = (
        reading.projected(recorded.projects, row, seen_at=SEEN_AT)
        for row in (rows if recorded.projects else ())
    )
    projected = tuple(one for one in kept if one is not None)
    more = slack.next_cursor(recorded.body)
    return Replayed(Expect.MORE_TO_READ if more else Expect.ANSWERED, projected)


def manifest() -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen builds, which is what ships."""
    from tests.unit import test_slack_messages as test_slack

    built: ConnectorManifest = test_slack.a_console_manifest()
    return built


def read_back_answer(recorded: Cassette) -> Verification:
    """One recording through Slack's read-back reading, as the list call it was made against."""
    said = slack.Reply(status=recorded.status, body=recorded.body)
    return answered(SOURCE, operation_of(recorded), said)


#: How each recording this connector's read-back names is answered. Every Slack list is a listing;
#: ok false inside a 200 is a refusal and proves nothing.
READ_BACK: Final[Mapping[str, Verification]] = MappingProxyType(
    {
        "SLACK-200-channels": Verification.FOUND,
        "SLACK-200-members": Verification.FOUND,
        "SLACK-200-membership": Verification.FOUND,
        "SLACK-200-history": Verification.FOUND,
        "SLACK-200-not-ok": Verification.INCONCLUSIVE,
        "SLACK-429": Verification.INCONCLUSIVE,
        "SLACK-503": Verification.INCONCLUSIVE,
    }
)


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    read_back=READ_BACK,
    read_back_answer=read_back_answer,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
