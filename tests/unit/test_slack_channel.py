"""The Slack channel, end to end: a request signed with the app's signing secret in, answers out on
the bot's token, and a secret of two parts kept whole.

Three halves. The wire, over Events API bodies built here the way Slack documents them, each
refusal beside what it accepts. The secret's parts, through the route that keeps them: both at
once or neither, never one new beside one old. And the events address, where a signed message from
somebody bound to nobody is answered in their own conversation with the app, on the bot's token,
and nothing else leaves.

Task ids: M10.5.1, M10.6.1
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.channels import adapter
from brain.channels.adapter import (
    BOT_ID,
    Arrived,
    ChannelRegistryError,
    VendorAnswer,
    channel_guides,
)
from brain.channels.slack import (
    BOT_TOKEN,
    GUIDE,
    MANIFEST,
    SIGNATURE_HEADER,
    SIGNING_SECRET,
    TIMESTAMP_HEADER,
    WIRE,
    SlackSecret,
    question_of,
    sign,
)
from brain.channels.webhook import WebhookRefusedError
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised, identity_hash
from brain.identity.bearer import TokenAuthority
from brain.ops.channel_store import channel_secret_ref
from brain.ops.connect_steps import EVENTS_ADDRESS_MARK
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.tables.channel import CHANNEL_SECRET_PREFIX, RefusedBecause
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier
from tests.unit.test_channel_pipeline import (
    Directory,
    Store,
    Transport,
    World,
    fresh_record,
    headers,
)

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason: nothing below is about the present.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
SIGNING = "slack-signing-secret-0123456789abcdef"
TOKEN = "xoxb-slack-bot-token-sentinel-0123"
KEPT = json.dumps({SIGNING_SECRET: SIGNING, BOT_TOKEN: TOKEN})
BOT = "U0BRAINBOT"
SENDER = "U0PERSON1"
ROOM = "C0FINANCE"
DM = "D0PRIVATE"
EVENTS = f"{API_PREFIX}/channels/slack/events"


def event(
    *,
    text: str = "what is left on the retainer?",
    channel: str = DM,
    kind: str = "im",
    user: str = SENDER,
    ts: str = "1551690000.000100",
    **extra: object,
) -> dict[str, Any]:
    body: dict[str, object] = {
        "type": "message",
        "channel": channel,
        "channel_type": kind,
        "user": user,
        "text": text,
        "ts": ts,
    }
    body.update(extra)
    return {"type": "event_callback", "team_id": "T0WORKSPACE", "event": body}


def arrived(body: bytes, *, secret: str = SIGNING, at: datetime = NOW) -> Arrived:
    stamp = str(int(at.timestamp()))
    return Arrived(
        headers={
            TIMESTAMP_HEADER.lower(): stamp,
            SIGNATURE_HEADER.lower(): sign(secret, stamp, body),
        },
        body=body,
    )


def read(payload: Mapping[str, Any]) -> Any:
    raw = json.dumps(payload).encode()
    return WIRE.read(WIRE.verify(arrived(raw), KEPT, NOW))


# ======================================================================== the wire, inbound


def test_a_direct_message_signed_by_slack_is_read_with_the_sender_s_own_conversation() -> None:
    """**The positive half of every refusal below.** The sender is Slack's user id, the reply goes
    to the conversation, and the sender's own conversation with the app is `user:` their id.

    Delete this and a wire refusing everything would pass every test here."""
    received = read(event())
    assert (received.event.channel, received.event.channel_identity) == (Channel.SLACK, SENDER)
    assert received.event.text == "what is left on the retainer?"
    assert received.event.external_id == f"{DM}:1551690000.000100"
    assert received.reply_to == f"channel:{DM}"
    conversation = received.conversation
    assert conversation is not None
    assert (conversation.shared, conversation.sender_to, conversation.aside_to) == (
        False,
        f"user:{SENDER}",
        "",
    )


def test_a_channel_message_naming_the_app_is_shared_addressed_and_asks_without_the_name() -> None:
    """**In a channel the app is named first, and the name is not the question.** The mentions
    that open the message go; one later in the sentence stays; every mention is kept as a digest
    for the rule that a shared conversation is answered only when it named the app.

    Delete this and the question would carry the app's id, or a room could be answered unasked."""
    received = read(
        event(text=f"<@{BOT}> what did <@U0OTHER1|ann> order?", channel=ROOM, kind="channel")
    )
    assert received.event.text == "what did <@U0OTHER1|ann> order?"
    conversation = received.conversation
    assert conversation is not None
    assert conversation.shared is True
    assert conversation.aside_to == f"aside:{ROOM}:{SENDER}"
    assert conversation.addressed == {
        identity_hash(Channel.SLACK, BOT),
        identity_hash(Channel.SLACK, "U0OTHER1"),
    }


@pytest.mark.parametrize(
    "tamper", ["another secret", "altered after signing", "signed long ago", "unsigned", "one part"]
)
def test_a_request_slack_did_not_send_is_refused_before_it_is_read(tamper: str) -> None:
    """**Only what the app's signing secret signed is believed**, over the exact bytes and the
    time, and a kept secret missing its signing part verifies nothing.

    Delete this and anybody who found the events address could post as anybody."""
    body = json.dumps(event()).encode()
    secret = KEPT
    match tamper:
        case "another secret":
            sent = arrived(body, secret="somebody-else-signing-secret-000000")
        case "altered after signing":
            sent = Arrived(
                headers=arrived(body).headers, body=body.replace(b"retainer", b"payroll")
            )
        case "signed long ago":
            sent = arrived(body, at=NOW - timedelta(hours=1))
        case "unsigned":
            sent = Arrived(headers={}, body=body)
        case _:
            sent, secret = arrived(body), json.dumps({BOT_TOKEN: TOKEN})
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(sent, secret, NOW)


def test_slack_s_address_check_is_answered_with_its_own_challenge() -> None:
    """Slack checks the address when it is saved and keeps retrying until the answer is its
    challenge. Delete this and the address never verifies, so no event is ever sent."""
    check = json.dumps({"type": "url_verification", "challenge": "c-3f9a", "token": "x"}).encode()
    assert WIRE.handshake(WIRE.verify(arrived(check), KEPT, NOW)) == {"challenge": "c-3f9a"}
    assert WIRE.handshake(arrived(json.dumps(event()).encode())) is None
    with pytest.raises(WebhookRefusedError):
        WIRE.handshake(arrived(json.dumps({"type": "url_verification"}).encode()))


@pytest.mark.parametrize(
    "payload",
    [
        event(bot_id="B0OTHER"),
        event(subtype="message_changed"),
        event(text=f"<@{BOT}>", channel=ROOM, kind="channel"),
        event(kind="huddle"),
        {"type": "event_callback", "event": {"type": "reaction_added"}},
    ],
)
def test_anything_but_a_person_s_question_is_unreadable(payload: dict[str, Any]) -> None:
    """Another app's message, an edit, a mention with no question, a conversation of no kind Slack
    names, and an event that is not a message. Delete this and the app could answer another bot
    for ever, or answer an empty question."""
    with pytest.raises(ValueError):
        read(payload)


def test_only_the_mentions_that_open_a_message_are_left_out() -> None:
    """Delete this and a question naming a colleague mid-sentence would lose who it is about."""
    assert question_of(f"<@{BOT}>  <@U0B2>  hello <@U0C3>") == "hello <@U0C3>"
    assert question_of("hello") == "hello"


# ======================================================================== the wire, outbound


@pytest.mark.parametrize(
    ("to", "method", "payload"),
    [
        (f"channel:{ROOM}", "chat.postMessage", {"channel": ROOM}),
        (f"user:{SENDER}", "chat.postMessage", {"channel": SENDER}),
        (f"aside:{ROOM}:{SENDER}", "chat.postEphemeral", {"channel": ROOM, "user": SENDER}),
        (ROOM, "chat.postMessage", {"channel": ROOM}),
    ],
)
def test_each_address_is_one_slack_method_on_the_bot_s_token(
    to: str, method: str, payload: dict[str, str]
) -> None:
    """**A reply leaves on the bot's token, to Slack's own host.** A conversation and a person's
    own conversation with the app post a message; one person inside a shared one gets it
    ephemerally; a test message names a bare id.

    Delete this and an aside could be posted for the whole room, or the token not sent."""
    request = WIRE.request_for(to=to, text="Twelve hours.", secret=KEPT, tenant={}, now=NOW)
    assert request.url == f"https://slack.com/api/{method}"
    assert request.method == "POST"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.body) == {**payload, "text": "Twelve hours."}
    assert request.exchange is None


@pytest.mark.parametrize(
    "to", ["", "channel:", "channel:not-an-id", "aside:C0ROOM", "mail:x@y.test", "user:U0A:U0B"]
)
def test_an_address_of_no_kind_is_refused(to: str) -> None:
    """Delete this and a malformed address could reach Slack as some other conversation."""
    with pytest.raises(ValueError):
        WIRE.request_for(to=to, text="x", secret=KEPT, tenant={}, now=NOW)


def test_a_text_longer_than_slack_keeps_is_refused_and_one_at_the_limit_is_not() -> None:
    """Slack cuts a message at 40,000 characters. Delete this and a long answer would arrive with
    its end, and whatever label it carried, missing."""
    WIRE.request_for(to=f"channel:{ROOM}", text="x" * 40_000, secret=KEPT, tenant={}, now=NOW)
    with pytest.raises(ValueError, match="longer"):
        WIRE.request_for(to=f"channel:{ROOM}", text="x" * 40_001, secret=KEPT, tenant={}, now=NOW)


@pytest.mark.parametrize(
    ("answer", "judged"),
    [
        (VendorAnswer(status=200, body=b'{"ok":true}'), CallOutcome.OK),
        (
            VendorAnswer(status=200, body=b'{"ok":false,"error":"channel_not_found"}'),
            CallOutcome.REJECTED,
        ),
        (VendorAnswer(status=200, body=b'{"ok":false,"error":"ratelimited"}'), CallOutcome.QUOTA),
        (VendorAnswer(status=200, body=b"not json"), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=429), CallOutcome.QUOTA),
        (VendorAnswer(status=503), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=400), CallOutcome.REJECTED),
        (VendorAnswer(status=204), CallOutcome.REJECTED),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
    ],
)
def test_the_wire_judges_slack_s_answer(answer: VendorAnswer, judged: CallOutcome) -> None:
    """Slack refuses inside a 200. Delete this and a refused message would be recorded as sent."""
    assert WIRE.judge(answer) is judged


def test_who_is_in_a_conversation_is_read_a_page_at_a_time_as_digests() -> None:
    """**The read a room's floor needs**, on the bot's token, each member digested at once.

    Delete this and a room's floor would be computed over nobody, or over raw member ids."""
    request = WIRE.members_request(
        conversation_id=ROOM, page="dXNlcjpVMEc5", secret=KEPT, tenant={}
    )
    parts = urlsplit(request.url)
    assert (parts.netloc, parts.path, request.method) == (
        "slack.com",
        "/api/conversations.members",
        "GET",
    )
    assert parse_qs(parts.query) == {
        "channel": [ROOM],
        "limit": ["200"],
        "cursor": ["dXNlcjpVMEc5"],
    }
    assert request.headers == {"Authorization": f"Bearer {TOKEN}"}
    page = json.dumps(
        {"ok": True, "members": [SENDER, BOT], "response_metadata": {"next_cursor": "next"}}
    ).encode()
    assert WIRE.members_page(VendorAnswer(status=200, body=page)) == (
        frozenset({identity_hash(Channel.SLACK, SENDER), identity_hash(Channel.SLACK, BOT)}),
        "next",
    )
    last = json.dumps({"ok": True, "members": [], "response_metadata": {"next_cursor": ""}})
    assert WIRE.members_page(VendorAnswer(status=200, body=last.encode())) == (frozenset(), "")


@pytest.mark.parametrize(
    "body",
    [
        b'{"ok":false,"error":"not_in_channel"}',
        b'{"ok":true,"members":"U0A"}',
        b'{"ok":true,"members":[""]}',
    ],
)
def test_an_answer_that_is_not_a_page_of_members_is_refused(body: bytes) -> None:
    """Delete this and a failed read would be taken for an empty room, whose floor is the
    asker's own."""
    with pytest.raises(ValueError):
        WIRE.members_page(VendorAnswer(status=200, body=body))


def test_a_refused_answer_is_not_a_page_even_when_it_lists_members() -> None:
    """**Slack's verdict decides first.** An answer Slack refused, or a server error, is not a
    page, whatever its body holds. Delete this and a refusal carrying a list, such as a cached or
    partial one, would be read as who is in the room."""
    listed = b'{"ok":true,"members":["U0PERSON1"]}'
    for answer in (
        VendorAnswer(status=503, body=listed),
        VendorAnswer(status=200, body=b'{"ok":false,"members":["U0PERSON1"]}'),
    ):
        with pytest.raises(ValueError, match="did not answer"):
            WIRE.members_page(answer)


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "not json",
        "[]",
        json.dumps({SIGNING_SECRET: SIGNING}),
        json.dumps({SIGNING_SECRET: "", BOT_TOKEN: TOKEN}),
    ],
)
def test_a_kept_secret_is_both_parts_or_nothing_is_sent(secret: str) -> None:
    """Delete this and a slot holding half a secret would send with an empty token."""
    with pytest.raises(ValueError):
        SlackSecret.parse(secret)
    assert SlackSecret.parse(KEPT) == SlackSecret(signing_secret=SIGNING, bot_token=TOKEN)
    assert TOKEN not in repr(SlackSecret.parse(KEPT))


# ======================================================================== the steps


def test_slack_s_steps_hold_its_form_once_and_check_the_address_after_it() -> None:
    """**The form need not be last.** Slack checks the address as it is saved, so the step that
    has it do that comes after the form that switches the channel on.

    Delete this and the steps could ask for the secret twice, or end before Slack can verify."""
    steps = channel_guides()[Channel.SLACK]
    forms = [one.key for one in steps if one.asks == (BOT_ID, SIGNING_SECRET, BOT_TOKEN)]
    assert forms == ["save"]
    assert [one.key for one in steps][-1] == "verify"
    manifest = json.loads(steps[0].copy_text)
    assert manifest["settings"]["event_subscriptions"]["request_url"] == EVENTS_ADDRESS_MARK
    assert set(manifest["settings"]["event_subscriptions"]["bot_events"]) == {
        "message.channels",
        "message.groups",
        "message.im",
        "message.mpim",
    }
    # Reading who is in each kind of conversation is what a room's floor needs.
    scopes = set(manifest["oauth_config"]["scopes"]["bot"])
    assert {"channels:read", "groups:read", "im:read", "mpim:read", "chat:write"} <= scopes


def _module(**attributes: object) -> ModuleType:
    made = ModuleType("brain.channels.stray")
    for key, value in attributes.items():
        setattr(made, key, value)
    return made


@pytest.mark.parametrize("which", ["two forms", "a stray ask"])
def test_a_guide_with_two_forms_or_asking_for_anything_else_is_refused(
    monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    """Delete this and a flow could collect a field the route refuses, or save twice."""
    real = list(adapter._channel_modules())
    extra = (
        replace(GUIDE[-2], key="again")
        if which == "two forms"
        else replace(GUIDE[0], key="more", asks=("region",))
    )
    stray = _module(GUIDE=(*GUIDE, extra), WIRE=WIRE)
    monkeypatch.setattr(adapter, "_channel_modules", lambda: iter([*real, stray]))
    with pytest.raises(ChannelRegistryError, match="form"):
        channel_guides()


# ======================================================================== the routes


@pytest.fixture
def world() -> World:
    here = World()
    here.secrets.slots[channel_secret_ref(Channel.SLACK).path] = KEPT
    here.records.kept[Channel.SLACK] = fresh_record(Channel.SLACK, tenant={BOT_ID: BOT})
    here.transport = Transport(answer=VendorAnswer(status=200, body=b'{"ok":true}'))
    return here


@pytest.fixture
def client(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", "https://brain.example.test/callback")
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = MemoryLedger()
        app.state.credentials = Credentials(world.vault)
        yield c


def post(c: TestClient, payload: Mapping[str, Any], *, secret: str = SIGNING) -> Any:
    raw = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    return c.post(
        EVENTS,
        content=raw,
        headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(secret, stamp, raw)},
    )


def test_a_direct_message_from_somebody_bound_to_nobody_is_answered_on_the_bot_s_token(
    client: TestClient, world: World
) -> None:
    """**End to end, through the events address.** The sender is bound to nobody, so the answer
    is the binding prompt, posted to their own conversation with the app on the bot's token.

    Delete this and every other test here is a test of a piece nobody showed the route."""
    answered = post(client, event())
    assert answered.status_code == 200, answered.text
    (sent,) = world.transport.sent
    assert sent.url == "https://slack.com/api/chat.postMessage"
    assert sent.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(sent.body) == {
        "channel": SENDER,
        "text": Unrecognised(channel=Channel.SLACK).prompt,
    }


def test_a_request_signed_with_another_secret_is_refused_and_nothing_is_sent(
    client: TestClient, world: World
) -> None:
    """Delete this and a forged event could make the app post on its token."""
    answered = post(client, event(), secret="somebody-else-signing-secret-000000")
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert world.transport.sent == []


def test_slack_s_address_check_through_the_route_gets_its_challenge_back(
    client: TestClient,
) -> None:
    """Delete this and the verify step the Connect Slack flow ends on could never pass."""
    answered = post(client, {"type": "url_verification", "challenge": "c-77", "token": "x"})
    assert (answered.status_code, answered.json()) == (200, {"challenge": "c-77"})


def test_both_parts_of_the_secret_are_kept_together_and_one_alone_is_refused(
    client: TestClient, world: World
) -> None:
    """**A secret of parts is written whole.** Both parts are kept in the channel's one slot as
    one object; one part alone, or a single `secret`, is refused and nothing is kept; saving with
    no secret at all keeps the ones held.

    Delete this and a record could hold a new signing secret beside an old token, which verifies
    and then sends on a token that no longer works, or the reverse."""
    path = f"{API_PREFIX}/channels/slack"
    as_admin = headers("u_admin")
    one = client.put(
        path,
        json={"enabled": True, "tenant": {BOT_ID: BOT}, "secret_parts": {SIGNING_SECRET: SIGNING}},
        headers=as_admin,
    )
    single = client.put(
        path, json={"enabled": True, "tenant": {BOT_ID: BOT}, "secret": SIGNING}, headers=as_admin
    )
    assert (one.status_code, single.status_code) == (422, 422)
    assert world.vault.slots == {}

    both = client.put(
        path,
        json={
            "enabled": True,
            "tenant": {BOT_ID: BOT},
            "secret_parts": {SIGNING_SECRET: SIGNING, BOT_TOKEN: TOKEN},
        },
        headers=as_admin,
    )
    assert both.status_code == 200, both.text
    kept = world.vault.slots[f"{CHANNEL_SECRET_PREFIX}slack"][KEY_FIELD]
    assert json.loads(kept) == {SIGNING_SECRET: SIGNING, BOT_TOKEN: TOKEN}
    assert SIGNING not in both.text and TOKEN not in both.text
    assert both.json()["secret_parts"] == [SIGNING_SECRET, BOT_TOKEN]

    webhook = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={
            "enabled": True,
            "tenant": {"reply_url": "https://hooks.example.test/r"},
            "secret_parts": {"x": "y"},
        },
        headers=as_admin,
    )
    assert webhook.status_code == 422


def test_the_manifest_is_served_with_this_install_s_events_address_in_it(
    client: TestClient,
) -> None:
    """Delete this and the manifest pasted into Slack would point its events nowhere."""
    found = client.get(f"{API_PREFIX}/channels", headers=headers("u_admin")).json()
    slack = next(one for one in found["channels"] if one["channel"] == "slack")
    manifest = json.loads(slack["steps"][0]["copy_text"])
    assert manifest["settings"]["event_subscriptions"]["request_url"] == (
        "https://brain.example.test/api/v1/channels/slack/events"
    )
    assert (
        json.loads(MANIFEST)["settings"]["event_subscriptions"]["request_url"]
        == EVENTS_ADDRESS_MARK
    )
