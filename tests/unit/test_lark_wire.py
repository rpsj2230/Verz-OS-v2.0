"""Lark on the events address: an event is signed, sealed and tokened or it is refused, and a reply
leaves with a token minted for it, to one of three audiences, judged by Lark's own code.

Every event is sealed by `tests/fixtures/lark_events.py`, written from Lark's algorithm rather than
from the module under test, and the decryption is held to Lark's own worked example. The
transport's token exchange is driven through `brain.channel_routes.HttpsTransport` over a sender
in memory, so what reaches the network is asserted request by request. No request reaches Lark.

Task ids: M10.2.1, M10.2.2, M10.2.5, M10.2.6, M10.6.1
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.channel_routes import HttpsTransport
from brain.channels.adapter import Arrived, VendorAnswer, VendorRequest
from brain.channels.lark import (
    AN_EVENT_IS_SIGNED_ENCRYPTED_AND_TOKENED_OR_REFUSED,
    EVENT_WINDOW,
    MAX_CARD_BYTES,
    WIRE,
    LarkSecret,
    open_event,
    question_of,
    verify_event,
)
from brain.channels.webhook import WebhookRefusedError
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.ops.outbox import SignedRequest
from brain.ops.outbox_store import SendResult
from brain.tools.fetch import Resolver
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    DOCUMENTED_KEY,
    DOCUMENTED_OPENED,
    DOCUMENTED_SEALED,
    ENCRYPT_KEY,
    RATE_LIMITED,
    REFUSED_IN_A_200,
    SENT,
    VERIFICATION_TOKEN,
    challenge,
    members_page,
    mention,
    message,
    seal,
    signed,
)

SECRET = LarkSecret(
    app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
).kept()
TENANT = {"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID}
ASKER = "ou_asker00000000000000000000001"


def arrived(raw: bytes, headers: dict[str, str]) -> Arrived:
    return Arrived(headers=headers, body=raw)


def now() -> datetime:
    return datetime.now(UTC)


# ================================================================ verifying (M10.2.1)


def test_the_documented_example_opens_to_its_documented_text() -> None:
    """Lark's own worked example, which nothing in this repository wrote. Delete this and the
    decryption and the fixture's seal could be wrong in the same way and agree."""
    assert open_event(DOCUMENTED_SEALED, DOCUMENTED_KEY) == DOCUMENTED_OPENED
    with pytest.raises(WebhookRefusedError):
        open_event(DOCUMENTED_SEALED, "another key")


def test_a_signed_sealed_event_verifies_and_is_read_opened() -> None:
    """The positive case every refusal below needs. Delete this and a wire that refused
    everything would pass the file."""
    raw, headers = signed(message(sender=ASKER, text="what is the price of WEB-1001"))
    opened = WIRE.verify(arrived(raw, headers), SECRET, now())
    assert json.loads(opened.body)["header"]["event_type"] == "im.message.receive_v1"
    assert WIRE.handshake(opened) is None
    received = WIRE.read(opened)
    assert received.event.channel is Channel.LARK
    assert received.event.text == "what is the price of WEB-1001"
    assert received.event.channel_identity == ASKER


@pytest.mark.parametrize(
    "how",
    ["signed by another key", "stale", "from the future", "tampered", "plaintext", "wrong token"],
)
def test_an_event_that_is_not_the_apps_own_is_refused(how: str) -> None:
    """`AN_EVENT_IS_SIGNED_ENCRYPTED_AND_TOKENED_OR_REFUSED`, one way at a time. Delete this and a
    forged, replayed or downgraded event is read as a colleague's question."""
    event = message(sender=ASKER, text="hello")
    late = int((now() - EVENT_WINDOW - timedelta(seconds=5)).timestamp())
    early = int((now() + EVENT_WINDOW + timedelta(seconds=5)).timestamp())
    if how == "signed by another key":
        raw, headers = signed(event, encrypt_key="somebody-elses-key")
    elif how == "stale":
        raw, headers = signed(event, at=late)
    elif how == "from the future":
        raw, headers = signed(event, at=early)
    elif how == "tampered":
        raw, headers = signed(event)
        raw = raw.replace(b'{"encrypt": "', b'{"encrypt":"')
    elif how == "plaintext":
        raw = json.dumps(event).encode()
        stamp = str(int(now().timestamp()))
        signature = hashlib.sha256((stamp + "n" + ENCRYPT_KEY).encode() + raw).hexdigest()
        headers = {
            "x-lark-request-timestamp": stamp,
            "x-lark-request-nonce": "n",
            "x-lark-signature": signature,
        }
    else:
        raw, headers = signed(message(sender=ASKER, text="hello", token="another-apps-token"))
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(raw, headers), SECRET, now())
    assert "signature is checked before anything is decrypted" in (
        AN_EVENT_IS_SIGNED_ENCRYPTED_AND_TOKENED_OR_REFUSED
    )


def test_a_bad_signature_is_refused_before_anything_is_decrypted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order is the rule: a request that does not verify is never opened. Delete this and an
    attacker's bytes reach the decryptor on the one path that exists to refuse them."""
    opened: list[str] = []
    import brain.channels.lark as lark

    real = lark.open_event

    def counted(encrypted: str, encrypt_key: str) -> bytes:
        opened.append("x")
        return real(encrypted, encrypt_key)

    monkeypatch.setattr(lark, "open_event", counted)
    raw, headers = signed(message(sender=ASKER, text="hi"), encrypt_key="somebody-elses-key")
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(raw, headers), SECRET, now())
    assert opened == []
    raw, headers = signed(message(sender=ASKER, text="hi"))
    WIRE.verify(arrived(raw, headers), SECRET, now())
    assert opened == ["x"]


def test_the_address_check_is_answered_unsigned_only_with_the_apps_token() -> None:
    """Lark checks the Request URL with an encrypted challenge that may carry no signature. It is
    echoed when it opens under the key and carries the token, and nothing else unsigned is. Delete
    this and either Lark cannot verify the address, or an unsigned event is let in as a check."""
    raw, headers = signed(challenge(), sign=False)
    opened = WIRE.verify(arrived(raw, headers), SECRET, now())
    assert WIRE.handshake(opened) == {"challenge": "challenge-0001"}
    wrong, headers = signed(challenge(token="another-apps-token"), sign=False)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(wrong, headers), SECRET, now())
    unsigned, headers = signed(message(sender=ASKER, text="hi"), sign=False)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(arrived(unsigned, headers), SECRET, now())


def test_a_secret_that_is_not_all_three_values_refuses_everything() -> None:
    """Delete this and a half-kept secret verifies with an empty key."""
    raw, headers = signed(message(sender=ASKER, text="hi"))
    for kept in ("", "{}", json.dumps({"app_secret": "a", "encrypt_key": ENCRYPT_KEY})):
        with pytest.raises(WebhookRefusedError):
            WIRE.verify(arrived(raw, headers), kept, now())
    parsed = LarkSecret.parse(SECRET)
    assert (parsed.app_secret, parsed.encrypt_key) == (APP_SECRET, ENCRYPT_KEY)
    assert " " not in SECRET and "\n" not in SECRET
    assert APP_SECRET not in repr(parsed)


def test_verification_reads_the_bytes_and_nothing_parsed() -> None:
    """Delete this and a parsed body could be verified, which the sender never signed."""
    with pytest.raises(TypeError):
        verify_event(
            secret=LarkSecret.parse(SECRET),
            body={"encrypt": seal(b"{}")},  # type: ignore[arg-type]
            timestamp="",
            nonce="",
            signature="",
            now=now(),
        )


# ================================================================ reading (M10.2.2, M10.2.6)


def test_a_direct_message_is_one_readers_conversation() -> None:
    """A p2p chat: shared is false, the room address is the chat, the sender's own address is
    their open id, and there is no aside. Delete this and a direct message is planned as a group."""
    raw, headers = signed(message(sender=ASKER, text="hello there"))
    received = WIRE.read(WIRE.verify(arrived(raw, headers), SECRET, now()))
    talk = received.conversation
    assert talk is not None
    assert (talk.shared, talk.aside_to) == (False, "")
    assert received.reply_to == talk.room_to == "chat:oc_chat0000000000000000000000001"
    assert talk.sender_to == f"user:{ASKER}"


def test_a_group_message_names_who_it_mentions_by_digest_and_offers_an_aside() -> None:
    """The bot's own mention is how a group message is known to be for it, keyed on the id; the
    placeholder is taken off the question and a colleague's becomes their name. Delete this and a
    group question reaches the gate as `@_user_1 ...` or is never known to be for the bot."""
    event = message(
        sender=ASKER,
        text="@_user_1 what did @_user_2 order",
        chat_type="group",
        mentions=[mention(BOT_OPEN_ID), mention("ou_colleague", key="@_user_2", name="Wei Ling")],
    )
    raw, headers = signed(event)
    received = WIRE.read(WIRE.verify(arrived(raw, headers), SECRET, now()))
    talk = received.conversation
    assert talk is not None and talk.shared
    assert identity_hash(Channel.LARK, BOT_OPEN_ID) in talk.addressed
    assert BOT_OPEN_ID not in "".join(talk.addressed)
    assert talk.aside_to == f"aside:oc_chat0000000000000000000000001:{ASKER}"
    assert received.event.text == "what did Wei Ling order"


def test_question_of_takes_opening_placeholders_off_and_leaves_unknown_ones() -> None:
    """Delete this and a question opening with two mentions keeps one, or a placeholder nobody
    named is replaced with nothing."""
    ids = [mention("a", "@_user_1", "Bot"), mention("b", "@_user_2", "Aaron")]
    assert question_of("@_user_1 @_user_2 hello", ids) == "hello"
    assert question_of("ask @_user_2 and @_user_9", ids) == "ask Aaron and @_user_9"
    assert question_of("@_user_1", ids) == ""


@pytest.mark.parametrize("kind", ["another event", "another app"])
def test_anything_but_a_persons_message_is_not_read(kind: str) -> None:
    """Delete this and a bot in the group, or an event nobody subscribed to, is answered."""
    event = (
        message(sender=ASKER, text="hi", event_type="im.chat.member.bot.added_v1")
        if kind == "another event"
        else message(sender=ASKER, text="hi", sender_type="app")
    )
    raw, headers = signed(event)
    opened = WIRE.verify(arrived(raw, headers), SECRET, now())
    with pytest.raises(ValueError):
        WIRE.read(opened)


# ================================================================ replying (M10.2.5, M10.6.1)


def _sent(request: VendorRequest) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(request.body)
    return parsed


def test_each_address_kind_is_its_own_request_with_a_token_exchange_beside_it() -> None:
    """A room posting, a direct message and a per-viewer card, each as Lark's API takes it, and
    each authorised by the App ID and App Secret exchanged for a token. Delete this and a private
    answer can go to the room's address, or a send goes out with no way to be authorised."""
    room = WIRE.request_for(to="chat:oc_1", text="a", secret=SECRET, tenant=TENANT, now=now())
    person = WIRE.request_for(to=f"user:{ASKER}", text="b", secret=SECRET, tenant=TENANT, now=now())
    aside = WIRE.request_for(
        to=f"aside:oc_1:{ASKER}", text="c", secret=SECRET, tenant=TENANT, now=now()
    )
    assert urlsplit(room.url).path == "/open-apis/im/v1/messages"
    assert parse_qs(urlsplit(room.url).query) == {"receive_id_type": ["chat_id"]}
    assert _sent(room)["receive_id"] == "oc_1" and json.loads(_sent(room)["content"]) == {
        "text": "a"
    }
    assert parse_qs(urlsplit(person.url).query) == {"receive_id_type": ["open_id"]}
    assert _sent(person)["receive_id"] == ASKER
    assert aside.url == "https://open.larksuite.com/open-apis/ephemeral/v1/send"
    card = _sent(aside)
    assert (card["chat_id"], card["open_id"], card["msg_type"]) == ("oc_1", ASKER, "interactive")
    assert card["card"]["elements"][0]["text"] == {"tag": "plain_text", "content": "c"}
    for request in (room, person, aside):
        assert request.method == "POST" and request.exchange is not None
        assert request.exchange.url.endswith("/open-apis/auth/v3/tenant_access_token/internal")
        assert json.loads(request.exchange.body) == {"app_id": APP_ID, "app_secret": APP_SECRET}
        assert request.exchange.answered_in == "tenant_access_token"
        assert APP_SECRET not in repr(request)


def test_a_reply_lark_cannot_take_is_refused_before_it_is_built() -> None:
    """Delete this and a malformed address or a record missing its platform is sent anyway."""
    for to, tenant in (
        ("room:oc_1", TENANT),
        ("aside:oc_1", TENANT),
        ("chat:", TENANT),
        ("chat:oc_1", {"app_id": APP_ID}),
        ("chat:oc_1", {"platform": "larksuite.com"}),
    ):
        with pytest.raises(ValueError):
            WIRE.request_for(to=to, text="t", secret=SECRET, tenant=tenant, now=now())
    with pytest.raises(ValueError):
        WIRE.request_for(
            to=f"aside:oc_1:{ASKER}",
            text="x" * (MAX_CARD_BYTES + 1),
            secret=SECRET,
            tenant=TENANT,
            now=now(),
        )
    feishu = WIRE.request_for(
        to="chat:oc_1",
        text="t",
        secret=SECRET,
        tenant=TENANT | {"platform": "feishu.cn"},
        now=now(),
    )
    assert feishu.url.startswith("https://open.feishu.cn/")


@pytest.mark.parametrize(
    ("answer", "judged"),
    [
        (VendorAnswer(status=200, body=json.dumps(SENT).encode()), CallOutcome.OK),
        (
            VendorAnswer(status=200, body=json.dumps(REFUSED_IN_A_200).encode()),
            CallOutcome.REJECTED,
        ),
        (VendorAnswer(status=200, body=json.dumps(RATE_LIMITED).encode()), CallOutcome.QUOTA),
        (VendorAnswer(status=400, body=json.dumps(RATE_LIMITED).encode()), CallOutcome.QUOTA),
        (
            VendorAnswer(status=400, body=json.dumps(REFUSED_IN_A_200).encode()),
            CallOutcome.REJECTED,
        ),
        (VendorAnswer(status=200, body=b"not json"), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=200), CallOutcome.UNAVAILABLE),
        (VendorAnswer(status=503), CallOutcome.UNAVAILABLE),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
    ],
)
def test_lark_is_judged_by_its_code_because_it_refuses_inside_a_200(
    answer: VendorAnswer, judged: CallOutcome
) -> None:
    """Delete this and a refusal inside a 200 is recorded as sent, which M10.6.1 forbids."""
    assert WIRE.judge(answer) is judged


def test_who_is_in_a_chat_is_read_by_digest_page_by_page() -> None:
    """The one read a group's floor needs, as a GET with the token beside it, and read into
    digests at once so no open id outlives it. Delete this and a floor is computed over raw ids
    that end up in a log, or over the first page of a large room."""
    first = WIRE.members_request(conversation_id="oc_1", page="", secret=SECRET, tenant=TENANT)
    assert first.method == "GET" and first.exchange is not None
    assert urlsplit(first.url).path == "/open-apis/im/v1/chats/oc_1/members"
    assert parse_qs(urlsplit(first.url).query) == {
        "member_id_type": ["open_id"],
        "page_size": ["100"],
    }
    later = WIRE.members_request(conversation_id="oc_1", page="p2", secret=SECRET, tenant=TENANT)
    assert parse_qs(urlsplit(later.url).query)["page_token"] == ["p2"]
    body = json.dumps(members_page([ASKER, "ou_other"], more="p2")).encode()
    digests, next_page = WIRE.members_page(VendorAnswer(status=200, body=body))
    assert digests == {identity_hash(Channel.LARK, ASKER), identity_hash(Channel.LARK, "ou_other")}
    assert next_page == "p2"
    last = json.dumps(members_page([ASKER])).encode()
    assert WIRE.members_page(VendorAnswer(status=200, body=last))[1] == ""
    for refused in (
        VendorAnswer(status=200, body=json.dumps(REFUSED_IN_A_200).encode()),
        VendorAnswer(status=200, body=b'{"code":0,"data":{"items":[{"name":"no id"}]}}'),
    ):
        with pytest.raises(ValueError):
            WIRE.members_page(refused)


# ================================================================ the transport


@dataclass
class Sender:
    """`HttpsSender` in memory: which method each request went by, and a fixed answer per path."""

    answers: dict[str, bytes] = field(default_factory=dict)
    seen: list[tuple[str, SignedRequest]] = field(default_factory=list)

    def _answer(self, how: str, request: SignedRequest) -> SendResult:
        self.seen.append((how, request))
        body = self.answers.get(urlsplit(request.url).path, json.dumps(SENT).encode())
        return SendResult(status=200, body=body)

    def send(self, request: SignedRequest) -> SendResult:
        return self._answer("send", request)

    def read(self, request: SignedRequest) -> SendResult:
        return self._answer("read", request)

    def mint(self, request: SignedRequest) -> SendResult:
        return self._answer("mint", request)


class Public:
    """A resolver that puts every name on a public address, as a vendor's is."""

    def resolve(self, host: str) -> list[str]:
        del host
        return ["8.8.8.8"]


TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"


def _transport(sender: Sender) -> HttpsTransport:
    resolver: Resolver = Public()
    return HttpsTransport(resolver=resolver, sender=sender)  # type: ignore[arg-type]


def test_a_send_mints_a_token_first_and_carries_it_and_nothing_keeps_it() -> None:
    """Delete this and a send goes out unauthorised, or with a token from an earlier send."""
    sender = Sender({TOKEN_PATH: b'{"code":0,"tenant_access_token":"t-1","expire":7200}'})
    request = WIRE.request_for(to="chat:oc_1", text="a", secret=SECRET, tenant=TENANT, now=now())
    answer = _transport(sender).send(request)
    assert WIRE.judge(answer) is CallOutcome.OK
    assert [how for how, _ in sender.seen] == ["mint", "send"]
    assert sender.seen[1][1].headers["Authorization"] == "Bearer t-1"
    assert "Authorization" not in request.headers


def test_a_refused_exchange_is_the_answer_and_nothing_is_sent() -> None:
    """Delete this and a wrong App Secret sends the reply unauthorised and records Lark's 401 as
    the vendor refusing the message rather than the credential."""
    sender = Sender({TOKEN_PATH: b'{"code":10014,"msg":"app secret invalid"}'})
    request = WIRE.request_for(to="chat:oc_1", text="a", secret=SECRET, tenant=TENANT, now=now())
    answer = _transport(sender).send(request)
    assert [how for how, _ in sender.seen] == ["mint"]
    assert WIRE.judge(answer) is CallOutcome.REJECTED


def test_a_read_goes_by_the_read_door_and_a_send_by_the_send_door_only() -> None:
    """`brain.ops.effects` holds every send to a key and lets a read through unkeyed, so the two
    must not be interchangeable. Delete this and a POST can be made through the door no key
    watches."""
    sender = Sender({TOKEN_PATH: b'{"code":0,"tenant_access_token":"t-1"}'})
    transport = _transport(sender)
    members = WIRE.members_request(conversation_id="oc_1", page="", secret=SECRET, tenant=TENANT)
    transport.read(members)
    assert [how for how, _ in sender.seen] == ["mint", "read"]
    reply = WIRE.request_for(to="chat:oc_1", text="a", secret=SECRET, tenant=TENANT, now=now())
    with pytest.raises(ValueError):
        transport.read(reply)
    with pytest.raises(ValueError):
        transport.send(members)


def test_the_kept_secret_is_one_line_the_vault_takes() -> None:
    """Delete this and the channel's secret is refused by the vault's one-piece rule on save."""
    from brain.ops.credentials import problems_with

    assert problems_with(SECRET) == ()
