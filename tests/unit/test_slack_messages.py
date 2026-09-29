"""Slack as a source, from its recordings: what is indexed, what is read live, and for whom.

Every reply here is one of `tests/fixtures/cassettes/slack_messages.py`'s recordings, driven
through the connector's own reading, projection and paging, or through
`brain.ops.slack_messages_live`'s reader with a caller that answers from those recordings and
opens no socket. The property the owner's guards name is tested from both sides: a message in a
private channel the asker is not in is never read, even when it is the best match, and the same
message is read once they are in it.

The Slack channel, which answers questions asked in Slack, is `brain.channels.slack` and is tested
in `tests/unit/test_slack.py`; this connector reads Slack as a source and shares nothing with it.

Task ids: M11.7.5
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors import slack_messages as slack
from brain.connectors.contract import AccessMode
from brain.connectors.declaration import SettingRefusedError, shipped
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.limits import SOURCE_CEILINGS
from brain.ops.slack_messages_live import READ_MESSAGE, SlackPassages
from tests.fixtures.cassettes import for_source
from tests.fixtures.cassettes._types import FETCHED_AT, SEEN_AT, Cassette
from tests.fixtures.cassettes.slack_messages import (
    MEMBER,
    MEMBER_EMAIL,
    PRIVATE_CHANNEL,
    PUBLIC_CHANNEL,
    UNINVITED_CHANNEL,
    operation_of,
)

WORKSPACE: Final = "T0123ABCD"
DEPARTMENT: Final = "operations"
#: A time far from any wall clock, so nothing here is about the present.
NOW: Final = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)


def console_settings(**changed: str) -> dict[str, str]:
    """What an administrator types on the Connectors screen to connect a workspace."""
    return {"workspace": WORKSPACE, "department": DEPARTMENT, **changed}


def a_console_manifest() -> Any:
    """The manifest a console connection builds, with the key where the console keeps it."""
    return manifest_for(slack.CONNECTOR_NAME, console_settings())


def recording(cid: str) -> Cassette:
    return next(one for one in for_source(slack.CONNECTOR_NAME) if one.cid == cid)


def kept_from(cid: str) -> dict[str, dict[str, Any]]:
    """What the reading keeps of one recording's rows, by source id."""
    recorded = recording(cid)
    reading = slack.SlackReading()
    reply = reading.interpret(
        operation_of(recorded), status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
    )
    assert reply.rows is not None
    kept = (
        reading.projected(recorded.projects, row.model_dump(), seen_at=SEEN_AT)
        for row in reply.rows.records
    )
    return {one.source_id: dict(one.fields) for one in kept if one is not None}


# ------------------------------------------------------------------ the connection
def test_a_workspace_is_named_by_its_id_and_answers_to_one_department() -> None:
    """The connection's scope is the one workspace typed, and its index answers to the department
    typed. Delete this and a connection could be pinned to nothing, or to whatever a lowercased id
    happens to match."""
    connection = slack.SlackConnection.from_settings(console_settings(workspace=" t0123abcd "))
    assert connection.scope().selectors == (WORKSPACE,)
    assert connection.visibility() == Scope.department(DEPARTMENT)


@pytest.mark.parametrize(
    ("settings", "setting"),
    [
        (console_settings(workspace="C0123ABCD"), "workspace"),
        (console_settings(workspace="acme.slack.com"), "workspace"),
        (console_settings(department="Operations Team"), "department"),
        (console_settings(department=""), "department"),
    ],
)
def test_a_setting_that_is_not_a_workspace_or_a_department_is_refused_by_name(
    settings: dict[str, str], setting: str
) -> None:
    """A channel id, a workspace address and a department's display name are each refused, naming
    the setting and quoting nothing typed. Delete this and a connection could be saved against a
    channel rather than a workspace, which no scope check would notice."""
    with pytest.raises(SettingRefusedError) as refused:
        slack.SlackConnection.from_settings(settings)
    assert refused.value.setting == setting
    assert not settings[setting] or settings[setting] not in str(refused.value)


# ------------------------------------------------------------------ the manifest
def test_the_manifest_is_read_only_service_identity_and_keeps_names_and_digests_alone() -> None:
    """The bot token is the app's, never a person's, and read-only; the index is a channel's name
    and privacy and a member's email digest, and nothing else. Delete this and a projection could
    widen to a channel's topic or a member's address with every other test green."""
    manifest = a_console_manifest()
    assert manifest.credential.mode is AccessMode.READ_ONLY
    assert {tool.identity_mode for tool in manifest.tools} == {IdentityMode.SERVICE}
    assert {tool.entity for tool in manifest.tools} == {slack.MESSAGE}
    assert {one.entity: tuple(f.name for f in one.fields) for one in manifest.projections} == {
        slack.CHANNEL: ("name", "privacy"),
        slack.MEMBER: ("identity_hash",),
    }


def test_the_connector_is_found_under_its_own_name_with_a_ceiling_of_its_own() -> None:
    """The name the module states is the one discovery found it under, and the ceiling its manifest
    names is a row `brain.ops.limits` holds, at Slack's lowest tier this connector calls. Delete
    this and the connector could be sized against another source's measured limit."""
    assert shipped()["slack_messages"] is slack.CONNECTOR
    assert slack.CONNECTOR.name == slack.CONNECTOR_NAME == slack.__name__.rsplit(".", 1)[-1]
    [ceiling] = [one for one in SOURCE_CEILINGS if one.name == a_console_manifest().ceiling]
    assert ceiling.name == "slack_messages"
    assert (ceiling.per_minute, ceiling.raisable) == (20, False)


def test_the_entities_name_no_other_surface_s_capability() -> None:
    """`read:member.*` is the console's whole member surface, so a Slack entity called `member`
    would have its steward granted that. Delete this and connecting Slack could hand its steward
    every member screen."""
    for entity in (slack.CHANNEL, slack.MEMBER, slack.MESSAGE):
        assert entity.startswith("slack_")
    assert READ_MESSAGE.value == "read:slack_message"


# ------------------------------------------------------------------ the index, from recordings
def test_only_the_channels_the_app_was_invited_to_are_kept_by_name_and_privacy() -> None:
    """A public channel the app is not in is listed by Slack and not kept, and a kept channel is
    its name and privacy alone. Delete this and the index lists every public channel in the
    workspace, and a topic could be kept."""
    kept = kept_from("SLACK-200-channels")
    assert kept == {
        PUBLIC_CHANNEL: {"name": "pricing", "privacy": "public"},
        PRIVATE_CHANNEL: {"name": "leadership", "privacy": "private"},
    }
    assert UNINVITED_CHANNEL not in kept


def test_a_member_is_kept_as_the_digest_of_a_confirmed_address_and_the_address_is_not() -> None:
    """The digest is the one an email binding keeps, so an asker is matched by it; an unconfirmed
    address, a deleted member and a bot are not kept, and the address itself is in no kept value.
    Delete this and a member could be matched by an address they never confirmed, which anybody
    can set, or the index could hold every address in the workspace."""
    kept = kept_from("SLACK-200-members")
    assert kept == {MEMBER: {"identity_hash": identity_hash(Channel.EMAIL, MEMBER_EMAIL)}}
    assert MEMBER_EMAIL not in json.dumps(kept)
    assert "workspace.example" not in json.dumps(kept)


def test_a_page_with_a_cursor_asks_for_the_next_and_an_empty_cursor_ends() -> None:
    """Slack's only paging signal. Delete this and the index stops at the first two hundred
    members, or asks for a page after the last for ever."""
    reading = slack.SlackReading()
    first = reading.first_page(slack.MEMBER)
    following = reading.next_page(slack.MEMBER, first, recording("SLACK-200-members").body, 4)
    assert following == {**first, "cursor": "dXNlcjpVMEc5V0ZYTlo="}
    body = recording("SLACK-200-channels").body
    assert reading.next_page(slack.CHANNEL, reading.first_page(slack.CHANNEL), body, 3) is None


def test_ok_false_inside_a_two_hundred_is_a_refusal_and_never_an_empty_workspace() -> None:
    """Slack answers a revoked token with 200 and ok false. The reading says the key was refused,
    and a real page is still read. Delete this and a revoked token reads as a workspace with no
    channels, and the index is emptied rather than the Connectors screen saying the key failed."""
    reading = slack.SlackReading()
    refused = recording("SLACK-200-not-ok")
    reply = reading.interpret(
        operation_of(refused), status=200, body=refused.body, fetched_at=FETCHED_AT
    )
    assert (reply.call, reply.rows) == (CallOutcome.REJECTED, None)
    good = recording("SLACK-200-channels")
    answered = reading.interpret(
        operation_of(good), status=200, body=good.body, fetched_at=FETCHED_AT
    )
    assert answered.call is CallOutcome.OK and answered.rows is not None


# ------------------------------------------------------------------ read live, per asker
@dataclass
class Recorded:
    """`SourceCaller` answering Slack's methods from the recordings, by method and channel."""

    member_of: tuple[str, ...]
    histories: dict[str, list[dict[str, Any]]]
    asked: list[str] = field(default_factory=list)
    headers_seen: list[dict[str, str]] = field(default_factory=list)

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        del address, max_bytes
        self.asked.append(url)
        self.headers_seen.append(dict(headers))
        split = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(split.query).items()}
        if split.path.endswith("/users.conversations"):
            assert query["user"] == MEMBER
            body: dict[str, Any] = {
                "ok": True,
                "channels": [{"id": one} for one in self.member_of],
                "response_metadata": {"next_cursor": ""},
            }
        elif split.path.endswith("/conversations.history"):
            body = {"ok": True, "messages": self.histories[query["channel"]]}
        else:
            body = {"ok": False, "error": "unknown_method"}
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())

    def read_history_of(self, channel: str) -> bool:
        return any("conversations.history" in one and channel in one for one in self.asked)


def message(ts: str, text: str) -> dict[str, Any]:
    return {"type": "message", "user": MEMBER, "ts": ts, "text": text}


#: The private channel's message holds every word of the question; the public one holds one.
HISTORIES: Final = {
    PUBLIC_CHANNEL: [message("1600000000.000100", "The retainer was discussed.")],
    PRIVATE_CHANNEL: [message("1600000200.000100", "The retainer price rises in March.")],
}
WORDS: Final = ("retainer", "price", "march")
CHANNELS: Final = {PUBLIC_CHANNEL: "pricing", PRIVATE_CHANNEL: "leadership"}


def a_connection() -> Connection:
    return Connection(
        connector=slack.CONNECTOR_NAME,
        settings=console_settings(),
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=NOW,
    )


def passages_over(caller: Recorded) -> SlackPassages:
    async def connected() -> Connection:
        return a_connection()

    return SlackPassages(
        connected,
        sessions=None,  # type: ignore[arg-type]  # `read` is driven directly and reads no table
        keys=_Keys(),
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: NOW,
    )


def test_a_private_channel_the_asker_is_not_in_is_never_read_even_holding_the_best_match() -> None:
    """**The owner's guard, from the refusing side.** Slack says the asker is in the public channel
    only, so the private channel's history is never asked for, and its message, which holds every
    word of the question, is not returned; the public channel's message is. Delete this and a
    leadership channel's message could answer a question from somebody who is not in it."""
    caller = Recorded(member_of=(PUBLIC_CHANNEL,), histories=HISTORIES)
    found = passages_over(caller).read(a_connection(), MEMBER, CHANNELS, WORDS)
    assert [(channel, text) for channel, _, text in found] == [
        (PUBLIC_CHANNEL, "The retainer was discussed.")
    ]
    assert not caller.read_history_of(PRIVATE_CHANNEL)
    assert all("price rises" not in text for _, _, text in found)


def test_the_same_private_message_is_read_first_once_the_asker_is_in_the_channel() -> None:
    """**The positive sibling.** With the asker in both channels, the private channel's message is
    read and ranked first, as the best match. Delete this and the refusal above could be a reader
    that never reads a private channel at all, which passes the guard and answers nothing."""
    caller = Recorded(member_of=(PUBLIC_CHANNEL, PRIVATE_CHANNEL), histories=HISTORIES)
    found = passages_over(caller).read(a_connection(), MEMBER, CHANNELS, WORDS)
    assert [channel for channel, _, _ in found] == [PRIVATE_CHANNEL, PUBLIC_CHANNEL]
    assert caller.read_history_of(PRIVATE_CHANNEL)


def test_membership_is_asked_of_slack_for_the_asker_with_the_bot_token() -> None:
    """Membership is asked for this member by id and nobody else, with the bot token as a bearer.
    Delete this and the reader could ask for another member's channels, or send no key."""
    caller = Recorded(member_of=(), histories=HISTORIES)
    assert passages_over(caller).read(a_connection(), MEMBER, CHANNELS, WORDS) == ()
    [asked] = caller.asked
    assert "users.conversations" in asked and f"user={MEMBER}" in asked
    assert caller.headers_seen[0]["Authorization"].startswith("Bearer ")


def test_a_channel_not_in_the_index_is_never_read_even_when_the_asker_is_in_it() -> None:
    """Only the channels the app was invited to, as the index lists them, are read: a channel
    Slack names for the member and the index does not list is not asked for. Delete this and the
    reader could read a channel the connection never listed."""
    caller = Recorded(member_of=(PUBLIC_CHANNEL, PRIVATE_CHANNEL), histories=HISTORIES)
    listed = {PUBLIC_CHANNEL: "pricing"}
    found = passages_over(caller).read(a_connection(), MEMBER, listed, WORDS)
    assert {channel for channel, _, _ in found} == {PUBLIC_CHANNEL}
    assert not caller.read_history_of(PRIVATE_CHANNEL)


# ------------------------------------------------------------------ the worker's read
def connect_slack(url: str) -> None:
    """Connect a workspace through the store the Connectors route writes with, no key kept."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connector_store import StoredConnections
    from tests.unit.test_connector_sync_run import through

    async def kept() -> datetime | None:
        return None

    through(
        url,
        lambda sessions: StoredConnections(sessions).connect(
            connector=slack.CONNECTOR_NAME,
            settings=console_settings(),
            digest=manifest_digest(a_console_manifest()),
            actor="u_admin",
            trace_id="t-connect",
            ent_hash="0" * 32,
            keep_key=kept,
        ),
    )


@pytest.mark.needs_db
def test_the_worker_reads_ok_false_as_a_declined_key_and_keeps_nothing() -> None:
    """**The worker's half of the refusal.** A revoked token answered with 200 and ok false is a
    declined key, down at once with the sentence that says to replace it, and nothing is kept.
    Delete this and `REFUSED_INSIDE_AN_ANSWER` could be dropped from the worker's run, which then
    reads the refusal as a workspace with no channels and records a successful read."""
    from brain.ops.connector_sync import KEY_DECLINED
    from tests.unit.test_connector_sync_run import Replay, a_database, attempts, projected, sync

    refused = recording("SLACK-200-not-ok")
    with a_database("brain_slack_messages_refused") as url:
        connect_slack(url)
        sync(url, Replay([SourceAnswer(status=200, body=json.dumps(refused.body).encode())]))
        ((outcome, health, _, _, failures, _, _, detail),) = attempts(url)
        kept = projected(url)
    assert (outcome, health, failures, detail) == ("failed", "down", 1, KEY_DECLINED)
    assert kept == []


@pytest.mark.needs_db
def test_the_worker_keeps_the_invited_channels_and_the_confirmed_members_digests() -> None:
    """**The positive sibling, from the same run.** An answered read keeps the two channels the
    app is in and the one member with a confirmed address, as a digest, and records a read to the
    end. Delete this and the refusal above could be a worker that reads Slack as nothing at all."""
    from tests.unit.test_connector_sync_run import Replay, a_database, attempts, projected, sync

    channels = recording("SLACK-200-channels").body
    members = {**recording("SLACK-200-members").body, "response_metadata": {"next_cursor": ""}}
    answers = [
        SourceAnswer(status=200, body=json.dumps(one).encode()) for one in (channels, members)
    ]
    with a_database("brain_slack_messages_read") as url:
        connect_slack(url)
        sync(url, Replay(answers))
        ((outcome, _, records, _, _, _, _, _),) = attempts(url)
        kept = projected(url)
    assert (outcome, records) == ("synced", 3)
    assert [(one[1], one[2]) for one in kept] == [
        (slack.CHANNEL, PUBLIC_CHANNEL),
        (slack.CHANNEL, PRIVATE_CHANNEL),
        (slack.MEMBER, MEMBER),
    ]
    assert MEMBER_EMAIL not in json.dumps([one[3] for one in kept])
