"""A Lark message through the real events address, answered by the web's own answer path.

The owner's done sentence for the Lark channel, clause by clause: a bound person asks in a direct
message and gets the same answer Ask gives them on the web; in a group each person gets an answer
at their own reach, privately or as a link, never another person's; an unbound sender gets the
binding prompt once. Each is driven here through `POST /api/v1/channels/lark/events` on the real
application, with an event sealed and signed as Lark seals it (`tests/fixtures/lark_events.py`),
the real answer lane over `tests/unit/test_api_routes.py`'s price list, and a Lark in memory that
answers with Lark's documented envelopes and records every request. The web answer each chat
answer is compared with is fetched from `/api/v1/answer` in the same test, as the same person.

Task ids: M10.2.2, M10.2.5, M10.2.6, M10.4.1, M10.4.2, M10.4.3, M10.4.4, M2.3.1, M1.8.5, M38.2.2.3
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.app import Settings, create_app
from brain.channels.inbound import CODE_REFUSED_TOLD, LINKED_TOLD, Redeemed
from brain.channels.lark import LarkSecret
from brain.chat_answer import (
    A_CHAT_ANSWER_IS_THE_WEB_ANSWER,
    LINK_TOLD,
    SOURCES_HEADING,
    chat_text,
)
from brain.core.principal import Principal
from brain.gate.answer import Answered
from brain.gate.context import Channel
from brain.gate.ingress import UNRECOGNISED_PROMPT, Binding, ChannelEvent, identity_hash
from brain.gate.streaming import citation_text
from brain.ops.channel_store import channel_secret_ref
from brain.tools.startup import build_registry
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    ENCRYPT_KEY,
    SENT,
    VERIFICATION_TOKEN,
    challenge,
    members_page,
    mention,
    message,
    signed,
)
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_answer_route import HOURS, OneRow, question
from tests.unit.test_api_routes import SOURCE, principal, wiring
from tests.unit.test_channel_pipeline import Claims, Deliveries, Records, Secrets, fresh_record
from tests.unit.test_streaming import decode

EVENTS = "/api/v1/channels/lark/events"
ORIGIN = "https://brain.example.test"
DM = "oc_dm00000000000000000000000000001"
GROUP = "oc_group000000000000000000000001"

#: Open ids, one per person, and who each is bound to. `ou_stranger` is bound to nobody.
OPEN_IDS: Mapping[str, str] = {
    "u_wide": "ou_wide000000000000000000000001",
    "u_narrow": "ou_narrow0000000000000000000001",
    "u_prefix": "ou_prefix0000000000000000000001",
    "u_elsewhere": "ou_elsewhere00000000000000000001",
}
STRANGER = "ou_stranger00000000000000000001"
WIDE = OPEN_IDS["u_wide"]


# ------------------------------------------------------------------------ Lark in memory


@dataclass
class Lark:
    """`ChannelTransport` answering as Lark: every send accepted, and who is in each group.

    `rooms` is a list of member lists per chat, read in turn, so a test can change the room
    between the read a floor is made from and the read that checks it before sending.
    """

    rooms: dict[str, list[list[str]]] = field(default_factory=dict)
    sent: list[Any] = field(default_factory=list)
    reads: list[Any] = field(default_factory=list)

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        assert request.exchange is not None
        assert json.loads(request.exchange.body) == {"app_id": APP_ID, "app_secret": APP_SECRET}
        self.sent.append(request)
        return VendorAnswer(status=200, body=json.dumps(SENT).encode())

    def read(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        chat = urlsplit(request.url).path.split("/")[-2]
        turns = self.rooms[chat]
        members = turns[min(len([one for one in self.reads if chat in one.url]), len(turns) - 1)]
        self.reads.append(request)
        return VendorAnswer(status=200, body=json.dumps(members_page(members)).encode())

    def messages(self) -> list[tuple[str, str, str]]:
        """Every message sent, as (kind, where, text), in order."""
        found: list[tuple[str, str, str]] = []
        for request in self.sent:
            body = json.loads(request.body)
            if request.url.endswith("/ephemeral/v1/send"):
                text = body["card"]["elements"][0]["text"]["content"]
                found.append(("aside", f"{body['chat_id']}:{body['open_id']}", text))
            else:
                kind = parse_qs(urlsplit(request.url).query)["receive_id_type"][0]
                text = json.loads(body["content"])["text"]
                found.append((kind, body["receive_id"], text))
        return found


class Bound:
    """`ChannelBindings` over `OPEN_IDS`: each open id's digest bound to its person."""

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        for pid, open_id in OPEN_IDS.items():
            if identity_hash(channel, open_id) == digest:
                return Binding(
                    channel=channel,
                    identity_hash=digest,
                    principal_id=pid,
                    bound_at=datetime(2019, 3, 4, 9, 0),
                )
        return None


class People:
    """The directory: everybody in `OPEN_IDS` is here and not disabled."""

    async def live(self, principal_id: str) -> Principal | None:
        return principal(principal_id) if principal_id in OPEN_IDS else None


@dataclass
class Binder:
    """`ChatBinder` that knows two codes, and what it was offered."""

    offered: list[str] = field(default_factory=list)

    async def redeem(self, event: ChannelEvent, text: str, *, now: datetime) -> Redeemed:
        self.offered.append(text)
        if text == "LINK-CODE-GOOD":
            return Redeemed.BOUND
        if text.startswith("LINK-CODE-"):
            return Redeemed.REFUSED
        return Redeemed.NOT_A_CODE


# ------------------------------------------------------------------------ the application


@dataclass
class World:
    lark: Lark = field(default_factory=Lark)
    records: Records = field(default_factory=Records)
    deliveries: Deliveries = field(default_factory=Deliveries)
    claims: Claims = field(default_factory=Claims)
    ledger: MemoryLedger = field(default_factory=MemoryLedger)


@pytest.fixture
def world() -> World:
    made = World()
    made.records.kept[Channel.LARK] = fresh_record(
        Channel.LARK,
        tenant={"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID},
    )
    return made


@pytest.fixture
def client(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", f"{ORIGIN}/callback")
    app: FastAPI = create_app(Settings(env="development"))
    kept = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (HOURS,)
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = Secrets({channel_secret_ref(Channel.LARK).path: kept})
        app.state.channel_transport = world.lark
        app.state.operation_ledger = world.ledger
        app.state.channel_bindings = Bound()
        app.state.chat_people = People()
        yield c


def post(c: TestClient, event: Mapping[str, Any]) -> Any:
    raw, headers = signed(event)
    return c.post(EVENTS, content=raw, headers=headers)


def dm(sender: str, text: str, ident: str) -> dict[str, Any]:
    return message(sender=sender, text=text, chat_id=DM, message_id=ident)


def in_group(sender: str, text: str, ident: str, *, to_bot: bool = True) -> dict[str, Any]:
    named = [mention(BOT_OPEN_ID)] if to_bot else [mention("ou_somebody", name="Somebody")]
    return message(
        sender=sender,
        text=f"@_user_1 {text}",
        chat_id=GROUP,
        chat_type="group",
        message_id=ident,
        mentions=named,
    )


#: A chat source line's read time, which is the instant of that read and differs between two.
READ_TIME = re.compile(r", (?:read|updated) [^)]*\)")


def undated(text: str) -> str:
    """Sources without the instant each was read at, so two reads of one record compare equal.

    The freshness words stay: whether a read is current is structure, and when it happened is not.
    """
    return READ_TIME.sub(")", text)


def web(c: TestClient, pid: str, text: str) -> tuple[list[str], list[str]]:
    """What the web's Ask streamed this person: the prose chunks and each citation as chat says it.

    The citation frames are fields; `citation_text` is the one reading of them a chat channel uses,
    so the web's sources are put in chat's words by the same function and then undated.
    """
    events = decode(question(c, text, pid).text)
    return (
        [one.data for one in events if one.event == "text"],
        [undated(citation_text(one.data)) for one in events if one.event == "citation"],
    )


# ======================================================================== the address check


def test_lark_s_check_of_the_address_is_echoed_and_claims_nothing(
    client: TestClient, world: World
) -> None:
    """The owner saves the Request URL in Lark and Lark verifies it at once. Delete this and the
    address can never be saved in Lark, which is the first thing the owner does."""
    raw, headers = signed(challenge(), sign=False)
    answered = client.post(EVENTS, content=raw, headers=headers)
    assert answered.status_code == 200
    assert answered.json() == {"challenge": "challenge-0001"}
    assert world.claims.asked == 0 and world.lark.sent == []


# ======================================================================== a direct message


def test_a_bound_person_is_answered_in_a_direct_message_as_ask_answers_them_on_the_web(
    client: TestClient, world: World
) -> None:
    """**M2.3.1 and M38.2.2.3: the same person, the same question, the same answer.** The chat
    reply is compared with what `/api/v1/answer` streams the same person, prose and sources, and
    it goes to the chat it came from and nowhere else. Delete this and the chat channel can answer
    from a second path whose reach or wording drifts from the web's."""
    ask = "what is the price of WEB-1001"
    accepted = post(client, dm(WIDE, ask, "om_dm_1"))
    assert accepted.status_code == 200
    assert accepted.json() == {"status": "accepted", "reply": None}
    ((kind, where, text),) = world.lark.messages()
    assert (kind, where) == ("chat_id", DM)
    prose, cited = web(client, "u_wide", ask)
    assert prose and cited
    assert text.startswith("".join(prose).strip())
    assert SOURCES_HEADING in text
    for one in cited:
        assert f"- {one}" in undated(text)
    assert "1200" in text
    assert world.deliveries.seen()[-1] == ("outbound", "sent", None)
    assert "the function the web's Ask runs" in A_CHAT_ANSWER_IS_THE_WEB_ANSWER


def test_two_people_asking_the_same_question_in_direct_messages_get_their_own_answers(
    client: TestClient, world: World
) -> None:
    """The same question at two reaches: u_wide may read the margin and u_narrow may not, and each
    chat reply carries exactly the sources the web gives that person. Delete this and every chat
    answer could be one person's, which a test of a single asker cannot see."""
    ask = "what is the price of WEB-1001"
    post(client, dm(WIDE, ask, "om_dm_2"))
    post(client, dm(OPEN_IDS["u_narrow"], ask, "om_dm_3"))
    wide, narrow = (undated(one[2]) for one in world.lark.messages())
    for pid, reply in (("u_wide", wide), ("u_narrow", narrow)):
        prose, cited = web(client, pid, ask)
        assert reply.startswith("".join(prose).strip())
        assert sorted(line[2:] for line in reply.splitlines() if line.startswith("- ")) == sorted(
            cited
        )
    assert "margin" in wide and "margin" not in narrow


def test_a_redelivered_event_is_answered_once(client: TestClient, world: World) -> None:
    """Lark posts again when it hears nothing within seconds. Delete this and a slow answer is
    sent twice."""
    event = dm(WIDE, "what is the price of WEB-1001", "om_dm_4")
    post(client, event)
    again = post(client, event)
    assert again.json() == {"status": "redelivered", "reply": None}
    assert len(world.lark.sent) == 1


# ======================================================================== an unbound sender


def test_an_unbound_sender_is_told_how_to_link_once_and_in_their_own_chat(
    client: TestClient, world: World
) -> None:
    """M10.3.3 and the owner's "once": the prompt goes to the sender's own chat with the bot, by
    open id, the first time, and a second message is not answered with it again. Delete this and a
    stranger is prompted on every message, or in front of a whole group."""
    post(client, dm(STRANGER, "hello", "om_s_1"))
    post(client, dm(STRANGER, "hello again", "om_s_2"))
    post(client, in_group(STRANGER, "and here", "om_s_3"))
    assert world.lark.messages() == [("open_id", STRANGER, UNRECOGNISED_PROMPT)]
    assert world.lark.reads == []


def test_a_group_message_not_for_the_bot_is_left_alone(client: TestClient, world: World) -> None:
    """M10.2.6. Delete this and a colleague talking to a colleague is answered, or prompted."""
    world.lark.rooms[GROUP] = [[WIDE, OPEN_IDS["u_narrow"]]]
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_0", to_bot=False))
    post(client, in_group(STRANGER, "hello", "om_g_00", to_bot=False))
    assert world.lark.sent == [] and world.lark.reads == []


# ======================================================================== binding (M1.8.5)


def test_a_code_sent_privately_is_offered_to_the_binder_and_the_answer_says_what_it_did(
    client: TestClient, world: World
) -> None:
    """The receiving half of binding by a one-time code: a message from somebody unbound, in a
    conversation only they read, is offered to the binder, which decides whether it is a code.
    Delete this and a code sent to the bot is answered with the prompt to send a code."""
    binder = Binder()
    client.app.state.channel_binder = binder  # type: ignore[attr-defined]
    post(client, dm(STRANGER, "LINK-CODE-GOOD", "om_b_1"))
    post(client, dm(STRANGER, "LINK-CODE-SPENT", "om_b_2"))
    post(client, dm(STRANGER, "what is this", "om_b_3"))
    assert binder.offered == ["LINK-CODE-GOOD", "LINK-CODE-SPENT", "what is this"]
    assert [one[2] for one in world.lark.messages()] == [
        LINKED_TOLD,
        CODE_REFUSED_TOLD,
        UNRECOGNISED_PROMPT,
    ]


def test_a_code_posted_in_a_group_binds_nobody(client: TestClient, world: World) -> None:
    """`A_CODE_IS_REDEEMED_ONLY_WHERE_THE_SENDER_ALONE_READS_IT`. Delete this and anybody in the
    group who reads the code first binds their own account to the person who made it."""
    binder = Binder()
    client.app.state.channel_binder = binder  # type: ignore[attr-defined]
    post(client, in_group(STRANGER, "LINK-CODE-GOOD", "om_b_4"))
    assert binder.offered == []
    assert world.lark.messages() == [("open_id", STRANGER, UNRECOGNISED_PROMPT)]


# ======================================================================== a group (M10.4)


def rooms(world: World, *people: Sequence[str]) -> None:
    world.lark.rooms[GROUP] = [list(one) for one in people]


def test_a_group_hears_only_what_everybody_in_it_may_and_the_asker_reads_the_rest_privately(
    client: TestClient, world: World
) -> None:
    """M10.4.1, M10.4.2 and M10.2.5. u_wide reads cost and margin, u_prefix reads the WEB- prices
    only. The room is answered at the floor of the two, and u_wide's own answer, with its sources,
    goes to them alone in a card only they see. Delete this and the asker's answer, computed at
    their reach, is posted where a colleague who may not read it does."""
    rooms(world, [WIDE, OPEN_IDS["u_prefix"]])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_1"))
    sent = world.lark.messages()
    assert [(kind, where) for kind, where, _ in sent] == [
        ("chat_id", GROUP),
        ("aside", f"{GROUP}:{WIDE}"),
    ]
    room, aside = (one[2] for one in sent)
    wide_prose, wide_cited = web(client, "u_wide", "what is the price of WEB-1001")
    assert aside.startswith("".join(wide_prose).strip())
    for one in wide_cited:
        assert f"- {one}" in undated(aside)
    assert any("margin" in one for one in wide_cited)
    assert "margin" not in room and "cost" not in room
    assert "1200" in room


def test_a_group_with_anybody_unbound_in_it_is_told_nothing_and_the_asker_reads_theirs(
    client: TestClient, world: World
) -> None:
    """A person bound to nobody holds nothing, so the room's floor is nothing and the room is
    posted nothing; the asker still reads their own answer privately. Delete this and a stranger
    in the group reads an answer made at a colleague's reach."""
    rooms(world, [WIDE, STRANGER])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_2"))
    ((kind, where, text),) = world.lark.messages()
    assert (kind, where) == ("aside", f"{GROUP}:{WIDE}")
    assert "1200" in text


def test_where_the_floor_answers_nothing_the_asker_reads_their_answer_alone(
    client: TestClient, world: World
) -> None:
    """u_elsewhere reaches the price list in a scope no row is in, so the floor's answer finds
    nothing and is not posted in front of the room; u_wide reads 1200 privately. Delete this and
    the room is shown an abstention beside every private answer, and learns the asker was told
    something."""
    rooms(world, [WIDE, OPEN_IDS["u_elsewhere"]])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_3"))
    ((kind, _, text),) = world.lark.messages()
    assert kind == "aside" and "1200" in text


def test_a_room_that_changes_while_the_answer_is_made_is_not_posted_the_old_answer(
    client: TestClient, world: World
) -> None:
    """M10.4.4. The room is read again before sending, and somebody joined who was not counted in
    the floor, so the room posting is dropped and only the asker's own card goes. Delete this and
    the newcomer reads an answer made at a floor they were never part of."""
    rooms(world, [WIDE, OPEN_IDS["u_prefix"]], [WIDE, OPEN_IDS["u_prefix"], STRANGER])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_4"))
    assert [kind for kind, _, _ in world.lark.messages()] == ["aside"]
    assert len(world.lark.reads) == 2


def test_a_group_where_everybody_holds_the_same_is_answered_in_the_room_once(
    client: TestClient, world: World
) -> None:
    """The positive sibling: nothing is withheld for the room, so the room reads the answer and
    there is no card beside it. Delete this and every group question is answered privately,
    which is a group channel nobody can use together."""
    rooms(world, [WIDE])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_5"))
    ((kind, where, text),) = world.lark.messages()
    assert (kind, where) == ("chat_id", GROUP)
    assert "1200" in text


def test_a_room_that_cannot_be_read_is_answered_as_a_floor_of_nothing(
    client: TestClient, world: World
) -> None:
    """A members read that fails, or a list the asker is not on, leaves the floor unknown, and
    unknown is nothing. Delete this and a failed read is taken for an empty room, whose floor is
    the asker's own reach."""
    rooms(world, [OPEN_IDS["u_narrow"]])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_6"))
    assert [kind for kind, _, _ in world.lark.messages()] == ["aside"]


def test_a_person_who_holds_nothing_in_a_room_that_holds_nothing_is_sent_a_link(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M10.4.3: nothing may be said and there is nothing to say privately, so the room is offered
    Ask, which carries nothing and runs the gate again for whoever follows it. Delete this and a
    question in such a room ends in silence."""
    from tests.unit import test_api_routes

    monkeypatch.setitem(test_api_routes.GRANTS, "u_narrow", ())
    rooms(world, [OPEN_IDS["u_narrow"], STRANGER])
    post(client, in_group(OPEN_IDS["u_narrow"], "what is the price of WEB-1001", "om_g_7"))
    ((kind, where, text),) = world.lark.messages()
    assert (kind, where) == ("chat_id", GROUP)
    assert text == f"{LINK_TOLD}{ORIGIN}/ask"


# ======================================================================== reading the frames


def test_the_chat_text_is_the_prose_then_the_sources_or_the_failure_alone() -> None:
    """Delete this and a failed answer's sentence is sent with the sources of nothing, or the
    sources are dropped."""
    from brain.gate.streaming import Event, encode

    frames = (
        encode(Event.CITATION, "price_list p_web_1: sell_price"),
        encode(Event.TEXT, "1200"),
        encode(Event.DONE, ""),
    )
    assert (
        chat_text(Answered(frames=frames)) == "1200\n\nSources:\n- price_list p_web_1: sell_price"
    )
    failed = (encode(Event.TEXT, "partial"), encode(Event.ERROR, "That did not work."))
    assert chat_text(Answered(frames=failed)) == "That did not work."


def test_a_structured_citation_reaches_chat_as_a_sentence_and_never_as_its_fields() -> None:
    """The web's citation frames are fields for the console to link. Chat reads them back into
    what the source is, how fresh it is, when, and its badge, and prints no field name or brace.

    Delete this and every chat answer ends in raw JSON lines, which is what shipped for one run."""
    from brain.gate.streaming import Event, encode

    record = {
        "kind": "record",
        "label": "price_list p_web_1: sell_price from local",
        "freshness": "stale",
        "freshness_text": "out of date",
        "read_at": "2019-03-02T09:05:00+00:00",
        "badge": "",
    }
    document = {
        "kind": "document",
        "label": "Handbook, section Leave from knowledge",
        "freshness": "live",
        "freshness_text": "current",
        "read_at": "2019-02-20T09:00:00+08:00",
        "badge": "verified",
    }
    undatable = {"kind": "record", "label": "x: y", "freshness_text": "read time not stated"}
    frames = (
        *(encode(Event.CITATION, json.dumps(one)) for one in (record, document, undatable)),
        encode(Event.TEXT, "1200"),
        encode(Event.DONE, ""),
    )

    text = chat_text(Answered(frames=frames))
    assert text.splitlines()[3:] == [
        "- price_list p_web_1: sell_price from local (out of date, read 02 Mar 2019 09:05 UTC)",
        "- Handbook, section Leave from knowledge (current, updated 20 Feb 2019) [verified]",
        "- x: y (read time not stated)",
    ]
    assert "{" not in text and "freshness" not in text


def test_a_surface_with_no_private_message_posts_the_floor_and_offers_the_rest_as_a_link(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M10.4.3's middle rung: an installation whose app may not send a card one person sees posts
    the room its floor and offers the asker a link for the rest, which carries nothing. Both go,
    to the one room address, each under its own key. Delete this and the asker's larger answer is
    either posted where the room reads it or silently lost."""
    from brain import chat_answer
    from brain.channels.adapter import Feature
    from brain.channels.lark import LarkAdapter

    monkeypatch.setattr(
        chat_answer, "adapter_for", lambda channel: LarkAdapter(features=frozenset({Feature.CARDS}))
    )
    rooms(world, [WIDE, OPEN_IDS["u_prefix"]])
    post(client, in_group(WIDE, "what is the price of WEB-1001", "om_g_8"))
    sent = world.lark.messages()
    assert [(kind, where) for kind, where, _ in sent] == [("chat_id", GROUP), ("chat_id", GROUP)]
    room, link = (one[2] for one in sent)
    assert "1200" in room and "margin" not in room
    assert link == f"{LINK_TOLD}{ORIGIN}/ask"


def test_an_answer_above_the_chats_ceiling_is_replaced_by_the_link(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M10.1.3 in chat: the most sensitive field in an answer is read from the redactor's own
    policies, and one above what Lark may carry is not sent; the person is sent Ask instead, which
    the console carries. Delete this and a restricted field reaches a phone's chat history, or an
    answer is refused by `deliver` and the person hears nothing."""
    from brain import chat_answer
    from brain.core.field_policy import Classification, FieldPolicy, FieldRule
    from brain.core.redaction import ChannelPayload

    payload = ChannelPayload(records=({"@entity": "price_list", "@id": "p", "cost": "1"},))
    policies = {
        "price_list": FieldPolicy(
            rules=(
                FieldRule.of(
                    "price_list", "cost", "read:price_list.cost", Classification.RESTRICTED
                ),
            )
        )
    }
    assert chat_answer.highest_in(payload, policies) is Classification.RESTRICTED
    assert chat_answer.highest_in(payload, {}) is Classification.INTERNAL
    monkeypatch.setattr(
        chat_answer, "highest_in", lambda payload, policies: Classification.RESTRICTED
    )
    post(client, dm(WIDE, "what is the price of WEB-1001", "om_dm_9"))
    ((kind, where, text),) = world.lark.messages()
    assert (kind, where) == ("chat_id", DM)
    assert text == f"{chat_answer.CEILING_TOLD}{ORIGIN}/ask"
