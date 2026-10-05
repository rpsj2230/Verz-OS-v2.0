"""The Telegram channel, end to end: the install tells Telegram where it is, updates carry a header
made from the bot token, and answers go out on the token.

Three parts. The wire, over Bot API bodies built here the way Telegram documents them, each refusal
beside what it accepts. The save route, which makes the `setWebhook` call before it keeps anything,
and keeps nothing Telegram refused. And the events address, where an update carrying the header the
install registered is answered and one carrying anything else is not.

Task ids: M10.5.4, M10.6.1
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.channels.adapter import (
    BOT_ID,
    SECRET_ASK,
    Arrived,
    RegisteredWire,
    RegistrationRefusedError,
    VendorAnswer,
    channel_guides,
    channel_wires,
)
from brain.channels.telegram import (
    AUTHENTICATING_HEADER,
    BOTFATHER_URL,
    MAX_TEXT_CHARS,
    MINIMUM_SECRET_LENGTH,
    NOT_A_BOT_USERNAME,
    NOT_AN_ADDRESS_TELEGRAM_POSTS_TO,
    NOT_WHAT_BOTFATHER_GIVES,
    TELEGRAM_API_URL,
    WEBHOOK_SECRET_PURPOSE,
    WIRE,
    question_of,
    webhook_secret_of,
)
from brain.channels.webhook import WebhookRefusedError
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised, identity_hash
from brain.identity.bearer import TokenAuthority
from brain.ops.channel_store import channel_secret_ref
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
TOKEN = "123456789:AAFtelegram-bot-token-sentinel_0123"
OTHER_TOKEN = "987654321:AAFanother-bot-token-sentinel_9876"
BOT = "company_brain_bot"
SENDER = 424242
GROUP = -1001234567890
EVENTS = f"{API_PREFIX}/channels/telegram/events"
ADDRESS = "https://brain.example.test/api/v1/channels/telegram/events"


def update(
    *,
    text: str = "what is left on the retainer?",
    chat: int = SENDER,
    kind: str = "private",
    sender: int = SENDER,
    update_id: int = 7001,
    **extra: object,
) -> dict[str, Any]:
    message: dict[str, object] = {
        "message_id": 11,
        "from": {"id": sender, "is_bot": False, "first_name": "Ada", "username": "ada_l"},
        "chat": {"id": chat, "type": kind},
        "date": int(NOW.timestamp()),
        "text": text,
    }
    message.update(extra)
    return {"update_id": update_id, "message": message}


def arrived(body: dict[str, Any], *, header: str | None = None) -> Arrived:
    sent = (
        {} if header == "" else {AUTHENTICATING_HEADER.lower(): header or webhook_secret_of(TOKEN)}
    )
    return Arrived(headers=sent, body=json.dumps(body).encode("utf-8"))


# ======================================================================== the header


def test_the_header_is_made_from_the_token_and_says_nothing_of_it() -> None:
    """**One value to paste, and a header an observer learns nothing from.** The header is the
    HMAC of a fixed purpose under the token: long enough for `assert_from_telegram`, inside the
    alphabet Telegram allows for it, different for another token, and not the token.

    Delete this and the header could be the token itself, handed to every proxy between Telegram
    and the install, or a value too short for the check that compares it."""
    made = webhook_secret_of(TOKEN)
    assert made == hmac.new(TOKEN.encode(), WEBHOOK_SECRET_PURPOSE, hashlib.sha256).hexdigest()
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", made)
    assert len(made) >= MINIMUM_SECRET_LENGTH
    assert TOKEN not in made and TOKEN.split(":")[1] not in made
    assert made != webhook_secret_of(OTHER_TOKEN)


def test_a_private_message_carrying_the_registered_header_is_read_as_its_numeric_sender() -> None:
    """The positive case: verified, then read as the gate's event, keyed on `from.id` and never on
    the username, and answered in the chat it came from, which is the sender's own.

    Delete this and every refusal below could be satisfied by a wire that refuses everything."""
    opened = WIRE.verify(arrived(update()), TOKEN, NOW)
    received = WIRE.read(opened)
    assert received.event.channel is Channel.TELEGRAM
    assert received.event.channel_identity == str(SENDER)
    assert received.event.external_id == "7001"
    assert received.event.text == "what is left on the retainer?"
    assert received.reply_to == str(SENDER)
    conversation = received.conversation
    assert conversation is not None
    assert (conversation.shared, conversation.sender_to, conversation.room_to) == (
        False,
        str(SENDER),
        str(SENDER),
    )


@pytest.mark.parametrize(
    "presented",
    [
        pytest.param(webhook_secret_of(OTHER_TOKEN), id="another bot's header"),
        pytest.param(TOKEN, id="the token itself"),
        pytest.param("", id="no header"),
        pytest.param("x" * 64, id="a guess"),
    ],
)
def test_an_update_carrying_any_other_header_is_refused(presented: str) -> None:
    """Delete this and anybody who learns the events address posts an update naming any user id,
    and is answered as that person, at that person's reach."""
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(update(), header=presented), TOKEN, NOW)


def test_a_secret_that_is_not_a_bot_token_refuses_every_update() -> None:
    """Delete this and a vault slot holding something else could make a header anybody can guess
    from it, or verify against nothing."""
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(update(), header=webhook_secret_of("short")), "short", NOW)


# ======================================================================== reading


def test_a_group_message_naming_the_bot_is_shared_addressed_and_has_nowhere_private() -> None:
    """**A group is shared, named by its mentions, and has no private address for the sender.**
    A mention's offset counts UTF-16 units, so a message opening with an emoji is sliced where
    Telegram means; a command addressed `@bot` and a reply to the bot's own message name it too.

    Delete this and a group message would be answered as though it were private, or never
    answered at all because the bot's name was sliced a character early."""
    text = "\N{GRINNING FACE} @company_brain_bot what is left?"
    mention = {"type": "mention", "offset": 3, "length": len("@company_brain_bot")}
    body = update(text=text, chat=GROUP, kind="supergroup", entities=[mention])
    received = WIRE.read(WIRE.verify(arrived(body), TOKEN, NOW))
    conversation = received.conversation
    assert conversation is not None
    assert conversation.shared and conversation.sender_to == ""
    assert conversation.room_to == str(GROUP) == received.reply_to
    assert identity_hash(Channel.TELEGRAM, BOT) in conversation.addressed

    command = {"type": "bot_command", "offset": 0, "length": len("/ask@company_brain_bot")}
    asked = update(
        text="/ask@company_brain_bot rates", chat=GROUP, kind="group", entities=[command]
    )
    replied = update(
        text="and for next month?",
        chat=GROUP,
        kind="group",
        reply_to_message={"message_id": 3, "from": {"id": 1, "is_bot": True, "username": BOT}},
    )
    unnamed = update(text="lunch?", chat=GROUP, kind="group")
    for named in (asked, replied):
        found = WIRE.read(WIRE.verify(arrived(named), TOKEN, NOW)).conversation
        assert found is not None and identity_hash(Channel.TELEGRAM, BOT) in found.addressed
    found = WIRE.read(WIRE.verify(arrived(unnamed), TOKEN, NOW)).conversation
    assert found is not None and found.addressed == frozenset()


def test_only_the_mentions_that_open_a_message_are_left_out() -> None:
    """Delete this and a question would reach the gate with the bot's name in it, or lose a name
    the person asked about."""
    assert question_of("@company_brain_bot what did @ada_l quote?") == "what did @ada_l quote?"
    assert question_of("  @a_bot @b_bot  hello") == "hello"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"update_id": 1, "edited_message": update()["message"]}, id="an edit"),
        pytest.param({"update_id": 2, "callback_query": {"id": "9"}}, id="a press"),
        pytest.param(
            {
                "update_id": 3,
                "message": {
                    **update()["message"],
                    "from": {"id": 5, "is_bot": True, "first_name": "Bot"},
                },
            },
            id="another bot",
        ),
        pytest.param(update(text="@company_brain_bot"), id="a name and nothing asked"),
    ],
)
def test_what_is_not_a_person_asking_is_not_read(body: dict[str, Any]) -> None:
    """Delete this and an edit re-answers a changed question, a press is read as a question, two
    bots answer each other, and a bare mention becomes a blank question."""
    with pytest.raises(ValueError, match=r"."):
        WIRE.read(WIRE.verify(arrived(body), TOKEN, NOW))


# ======================================================================== sending


def test_a_reply_is_sent_with_send_message_on_the_token_to_one_chat() -> None:
    """Delete this and the answer could go to another host, or to a chat named some other way."""
    made = WIRE.request_for(to=str(SENDER), text="Hello.", secret=TOKEN, tenant={}, now=NOW)
    assert made.url == f"{TELEGRAM_API_URL}/bot{TOKEN}/sendMessage"
    assert made.method == "POST"
    assert json.loads(made.body) == {"chat_id": SENDER, "text": "Hello."}
    assert TOKEN not in repr(made)


@pytest.mark.parametrize("to", ["@ada_l", "12 34", "", "https://example.test/", "1.5"])
def test_a_reply_to_anything_but_a_chat_id_is_refused(to: str) -> None:
    """Delete this and a test message typed as a username or an address would be posted as one."""
    with pytest.raises(ValueError, match="chat id"):
        WIRE.request_for(to=to, text="Hello.", secret=TOKEN, tenant={}, now=NOW)


def test_a_reply_longer_than_telegram_delivers_or_on_no_token_is_refused() -> None:
    """Delete this and Telegram's own refusal of a long message would be recorded as a vendor
    failure, or a malformed slot would be put in the address."""
    with pytest.raises(ValueError, match="longer"):
        WIRE.request_for(
            to=str(SENDER), text="x" * (MAX_TEXT_CHARS + 1), secret=TOKEN, tenant={}, now=NOW
        )
    WIRE.request_for(to=str(SENDER), text="x" * MAX_TEXT_CHARS, secret=TOKEN, tenant={}, now=NOW)
    with pytest.raises(ValueError, match="BotFather"):
        WIRE.request_for(to=str(SENDER), text="Hello.", secret="nope", tenant={}, now=NOW)


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (VendorAnswer(status=200, body=b'{"ok":true,"result":{}}'), CallOutcome.OK),
        (VendorAnswer(status=200, body=b'{"ok":false}'), CallOutcome.REJECTED),
        (VendorAnswer(status=200, body=b"<html>"), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=401, body=b'{"ok":false}'), CallOutcome.REJECTED),
        (VendorAnswer(status=429, body=b'{"ok":false}'), CallOutcome.QUOTA),
        (VendorAnswer(status=502), CallOutcome.UNAVAILABLE),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=302), CallOutcome.REJECTED),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
    ],
)
def test_the_wire_judges_the_bot_api_s_answer(answer: VendorAnswer, outcome: CallOutcome) -> None:
    """Delete this and a refusal inside a 200 would be recorded as sent, or a redirect followed."""
    assert WIRE.judge(answer) is outcome


# ======================================================================== registering


def test_the_registration_names_the_events_address_the_header_and_one_update_kind() -> None:
    """**What the install tells Telegram is what it then believes.** The call goes to the Bot API
    on the token, names this install's events address, the header made from the token, and asks
    for messages alone.

    Delete this and the header Telegram sends could differ from the one `verify` expects, which
    refuses every update, or Telegram could be asked for edits and presses nothing here reads."""
    told = WIRE.registration_for(address=ADDRESS, secret=TOKEN, tenant={BOT_ID: BOT})
    assert told.url == f"{TELEGRAM_API_URL}/bot{TOKEN}/setWebhook"
    assert json.loads(told.body) == {
        "url": ADDRESS,
        "secret_token": webhook_secret_of(TOKEN),
        "allowed_updates": ["message"],
    }
    posted = arrived(update(), header=json.loads(told.body)["secret_token"])
    assert WIRE.verify(posted, TOKEN, NOW) is posted


@pytest.mark.parametrize(
    ("address", "secret", "bot", "told"),
    [
        ("http://brain.example.test/e", TOKEN, BOT, NOT_AN_ADDRESS_TELEGRAM_POSTS_TO),
        ("https://brain.example.test:8080/e", TOKEN, BOT, NOT_AN_ADDRESS_TELEGRAM_POSTS_TO),
        (ADDRESS, TOKEN, "@company_brain_bot", NOT_A_BOT_USERNAME),
        (ADDRESS, TOKEN, "", NOT_A_BOT_USERNAME),
        (ADDRESS, "not-a-token", BOT, NOT_WHAT_BOTFATHER_GIVES),
    ],
)
def test_a_set_up_telegram_cannot_be_told_about_is_refused_in_words(
    address: str, secret: str, bot: str, told: str
) -> None:
    """Delete this and Telegram's own refusal of a port or a malformed token would reach the
    person as a vendor failure, or a username with an @ would be saved and never match a mention."""
    with pytest.raises(RegistrationRefusedError) as refused:
        WIRE.registration_for(address=address, secret=secret, tenant={BOT_ID: bot})
    assert str(refused.value) == told
    WIRE.registration_for(
        address="https://brain.example.test:8443/e", secret=TOKEN, tenant={BOT_ID: BOT}
    )


def test_telegram_is_the_one_channel_that_registers_its_address_on_save() -> None:
    """Delete this and another channel could start calling its vendor from the save route, or
    Telegram could stop being told where the install is."""
    assert {
        channel for channel, wire in channel_wires().items() if isinstance(wire, RegisteredWire)
    } == {Channel.TELEGRAM}


def test_telegram_s_steps_ask_only_the_username_and_the_token() -> None:
    """Delete this and the flow could ask for an events address nobody pastes anywhere, or for a
    webhook secret the install makes itself."""
    steps = channel_guides()[Channel.TELEGRAM]
    assert [one.key for one in steps] == ["bot", "groups", "save"]
    assert steps[0].link == BOTFATHER_URL
    assert [one.asks for one in steps] == [(), (), (BOT_ID, SECRET_ASK)]


# ======================================================================== the routes


@pytest.fixture
def world() -> World:
    here = World()
    here.secrets.slots[channel_secret_ref(Channel.TELEGRAM).path] = TOKEN
    here.records.kept[Channel.TELEGRAM] = fresh_record(Channel.TELEGRAM, tenant={BOT_ID: BOT})
    here.transport = Transport(answer=VendorAnswer(status=200, body=b'{"ok":true,"result":true}'))
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


def save(c: TestClient, **body: object) -> Any:
    asked = {"enabled": True, "tenant": {BOT_ID: BOT}, **body}
    return c.put(f"{API_PREFIX}/channels/telegram", json=asked, headers=headers("u_admin"))


def test_saving_the_set_up_tells_telegram_the_address_and_keeps_the_token(
    client: TestClient, world: World
) -> None:
    """**End to end through the save route.** Telegram is told this install's events address and
    the header made from the token being saved, and only then is the token kept.

    Delete this and a saved set-up could leave Telegram posting nowhere, which looks connected on
    every screen and answers nobody."""
    saved = save(client, secret=OTHER_TOKEN)
    assert saved.status_code == 200, saved.text
    (told,) = world.transport.sent
    assert told.url == f"{TELEGRAM_API_URL}/bot{OTHER_TOKEN}/setWebhook"
    assert json.loads(told.body)["url"] == ADDRESS
    assert json.loads(told.body)["secret_token"] == webhook_secret_of(OTHER_TOKEN)
    assert world.vault.slots[f"{CHANNEL_SECRET_PREFIX}telegram"][KEY_FIELD] == OTHER_TOKEN
    assert OTHER_TOKEN not in saved.text


def test_saving_without_a_new_token_registers_with_the_one_held(
    client: TestClient, world: World
) -> None:
    """Delete this and switching a field or re-saving would call Telegram on no token, or refuse
    a set-up whose token is already in the vault."""
    saved = save(client)
    assert saved.status_code == 200, saved.text
    (told,) = world.transport.sent
    assert told.url == f"{TELEGRAM_API_URL}/bot{TOKEN}/setWebhook"
    assert world.vault.slots == {}


def test_a_set_up_telegram_refused_is_not_saved_and_the_old_token_stays(
    client: TestClient, world: World
) -> None:
    """**A refusal keeps nothing.** Telegram answering 401 leaves the vault and the record as they
    were, and says in words that the set-up was not saved.

    Delete this and a mistyped token would replace the one that works, and the header the live
    registration sends would stop matching."""
    world.transport.answer = VendorAnswer(status=401, body=b'{"ok":false}')
    before = world.records.kept[Channel.TELEGRAM]
    refused = save(client, secret=OTHER_TOKEN, enabled=False)
    assert refused.status_code == 502
    assert refused.json()["message"] == channel_routes.REGISTRATION_TOLD[CallOutcome.REJECTED]
    assert world.vault.slots == {}
    assert world.records.kept[Channel.TELEGRAM] is before


def test_a_username_with_an_at_is_refused_in_words_and_telegram_is_not_called(
    client: TestClient, world: World
) -> None:
    """Delete this and a set-up whose mentions can never match would be saved, or its refusal
    shown as a vendor failure."""
    refused = save(client, tenant={BOT_ID: "@company_brain_bot"}, secret=OTHER_TOKEN)
    assert refused.status_code == 422
    assert refused.json()["message"] == NOT_A_BOT_USERNAME
    assert world.transport.sent == [] and world.vault.slots == {}


def test_an_install_with_no_public_address_cannot_save_telegram(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and Telegram would be told a relative path, or nothing, and the set-up saved as
    though it were connected."""
    monkeypatch.setattr(channel_routes, "events_address_of", lambda channel: "")
    refused = save(client, secret=OTHER_TOKEN)
    assert refused.status_code == 409
    assert refused.json()["message"] == channel_routes.NO_PUBLIC_ADDRESS
    assert world.transport.sent == [] and world.vault.slots == {}


def test_a_private_message_from_somebody_bound_to_nobody_is_answered_on_the_token(
    client: TestClient, world: World
) -> None:
    """**End to end, through the events address.** The sender is bound to nobody, so the answer
    is the binding prompt, sent to their own chat with the bot on the token.

    Delete this and every other test here is a test of a piece nobody showed the route."""
    answered = client.post(
        EVENTS,
        content=json.dumps(update()).encode(),
        headers={AUTHENTICATING_HEADER: webhook_secret_of(TOKEN)},
    )
    assert answered.status_code == 200, answered.text
    (sent,) = world.transport.sent
    assert sent.url == f"{TELEGRAM_API_URL}/bot{TOKEN}/sendMessage"
    assert json.loads(sent.body) == {
        "chat_id": SENDER,
        "text": Unrecognised(channel=Channel.TELEGRAM).prompt,
    }


def test_an_update_with_another_header_is_refused_and_nothing_is_sent(
    client: TestClient, world: World
) -> None:
    """Delete this and a forged update could make the bot speak on its token."""
    answered = client.post(
        EVENTS,
        content=json.dumps(update()).encode(),
        headers={AUTHENTICATING_HEADER: webhook_secret_of(OTHER_TOKEN)},
    )
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert world.transport.sent == []
