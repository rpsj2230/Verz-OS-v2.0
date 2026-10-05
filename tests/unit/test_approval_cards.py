"""Approval cards in Lark: offered to the approver alone, decided by their press alone, then closed.

Driven through `POST /api/v1/channels/lark/events` on the real application, with events and card
callbacks sealed and signed as Lark seals them, the Approvals route's own `take_decision` over an
in-memory suspension store that keeps a real audit chain, and a Lark in memory that records every
request. The admission half and the text half are asked directly: a card press is the one chat
act that carries `approve`, and a message meaning approve decides nothing on any channel.

Task ids: M10.2.3, M10.2.4, M10.7.1
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.app import Settings, create_app
from brain.approval_cards import (
    CLOSED_TOLD,
    DECIDED_TOLD,
    PRESS_REFUSED_TOLD,
    REJECTION_WORDS,
    HeldCardWindows,
    carries_cards,
)
from brain.approval_routes import DecidableVerdict, DecisionAsked, RejectionReason, take_decision
from brain.channels.adapter import Arrived, CardAction, VendorAnswer, adapter_for
from brain.channels.cards import (
    FALLBACK_TEMPLATE,
    CardCall,
    CardRefusedError,
    CardStaleError,
    PatchOutcome,
    card_limit,
    close_admitted,
    render_decided,
)
from brain.channels.inbound import (
    DECIDE_WHERE_TOLD,
    Inbound,
    Receipt,
    ReceiptKind,
    is_decision_reply,
    reply_for,
)
from brain.channels.lark import WIRE, LarkSecret
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.gate.addressing import from_mention
from brain.gate.admission import Assurance, admit, admit_card_press
from brain.gate.context import Channel
from brain.gate.ingress import Binding, ChannelEvent
from brain.gate.leash import ApprovalState, SuspendedAction
from brain.knowledge.visibility import PROMOTION_CAPABILITY
from brain.ops.channel_store import channel_secret_ref
from brain.ops.limits import LimiterState, WindowState
from brain.tools.startup import build_registry
from tests.fixtures.lark_events import (
    APP_ID,
    APP_SECRET,
    BOT_OPEN_ID,
    ENCRYPT_KEY,
    REFUSED_IN_A_200,
    SENT,
    VERIFICATION_TOKEN,
    mention,
    message,
    signed,
)
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_answer_route import HOURS, OneRow
from tests.unit.test_api_routes import GRANTS, SOURCE, WHOLE, wiring
from tests.unit.test_approval_decisions import MemoryStore
from tests.unit.test_channel_pipeline import Claims, Deliveries, Records, Secrets, fresh_record
from tests.unit.test_chat_answer import OPEN_IDS, Bound, People

ROOT = Path(__file__).resolve().parents[2]
EVENTS = "/api/v1/channels/lark/events"
ORIGIN = "https://brain.example.test"
DM = "oc_dm00000000000000000000000000001"
GROUP = "oc_group000000000000000000000001"
CARD_MESSAGE = "om_card000000000000000000000001"
WIDE, NARROW = OPEN_IDS["u_wide"], OPEN_IDS["u_narrow"]
APPROVE = Grant(capability=PROMOTION_CAPABILITY, scope=WHOLE)


# ------------------------------------------------------------------------ Lark in memory


@dataclass
class Lark:
    """`ChannelTransport` answering as Lark and keeping every request; `refuse_edits` answers a
    card replacement with Lark's refusal inside a 200."""

    sent: list[Any] = field(default_factory=list)
    refuse_edits: bool = False

    def send(self, request: Any) -> Any:
        self.sent.append(request)
        refused = self.refuse_edits and request.method == "PATCH"
        return VendorAnswer(
            status=200, body=json.dumps(REFUSED_IN_A_200 if refused else SENT).encode()
        )

    def read(self, request: Any) -> Any:
        raise AssertionError("nothing about an approval card reads who is in a chat")

    def posted(self) -> list[tuple[str, str, str, dict[str, Any] | None]]:
        """Every message and card posted, as (id kind, where, text, card), in order."""
        found: list[tuple[str, str, str, dict[str, Any] | None]] = []
        for request in self.sent:
            if request.method != "POST":
                continue
            body = json.loads(request.body)
            kind = parse_qs(urlsplit(request.url).query)["receive_id_type"][0]
            content = json.loads(body["content"])
            if body["msg_type"] == "interactive":
                found.append(
                    (kind, body["receive_id"], content["elements"][0]["text"]["content"], content)
                )
            else:
                found.append((kind, body["receive_id"], content["text"], None))
        return found

    def edits(self) -> list[tuple[str, dict[str, Any]]]:
        """Every card replaced in place, as (message id, the card it became)."""
        return [
            (urlsplit(one.url).path.rsplit("/", 1)[-1], json.loads(json.loads(one.body)["content"]))
            for one in self.sent
            if one.method == "PATCH"
        ]


@dataclass
class World:
    lark: Lark = field(default_factory=Lark)
    records: Records = field(default_factory=Records)
    deliveries: Deliveries = field(default_factory=Deliveries)
    claims: Claims = field(default_factory=Claims)
    ledger: MemoryLedger = field(default_factory=MemoryLedger)
    store: MemoryStore = field(default_factory=MemoryStore)
    windows: HeldCardWindows = field(default_factory=HeldCardWindows)
    #: The install's Approve from Lark cards switch for this test. On, unless a test turns it off.
    switched_on: bool = True


def a_promotion(asker: str) -> SuspendedAction:
    """A promotion raised by `asker`, as the promotion route raises one."""
    from brain.knowledge.promotion import raise_promotion
    from brain.knowledge.visibility import Visibility, propose_promotion

    now = datetime.now(UTC)
    proposal = propose_promotion(
        item_id="upload.handover",
        from_level=Visibility.DEPARTMENT,
        to_level=Visibility.COMPANY,
        proposer_id=asker,
        owner_id=asker,
        review_by=now + timedelta(days=180),
        reason="every team quotes from this",
        now=now,
    )
    return raise_promotion(
        proposal,
        title="Site handover",
        kind=None,
        department="maintenance",
        reach=EntitlementSet(principal_id=asker),
        trace_id="trace_test",
        now=now,
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    """A Lark record, a promotion asked by `u_prefix`, and `u_wide` and `u_elsewhere` holding the
    approval it needs; `u_narrow` holds none."""
    made = World()
    made.records.kept[Channel.LARK] = fresh_record(
        Channel.LARK,
        tenant={"app_id": APP_ID, "platform": "larksuite.com", "bot_id": BOT_OPEN_ID},
    )
    monkeypatch.setitem(GRANTS, "u_wide", (*GRANTS["u_wide"], APPROVE))
    monkeypatch.setitem(GRANTS, "u_elsewhere", (*GRANTS["u_elsewhere"], APPROVE))
    promotion = a_promotion("u_prefix")
    made.store.rows[promotion.id] = promotion
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
        app.state.suspensions = world.store
        app.state.card_windows = world.windows
        # The switch as `World.switched_on` says, so a test states the state it exercises.
        app.state.approve_from_cards = world.switched_on
        yield c


def post(c: TestClient, event: Mapping[str, Any], *, nonce: str | None = None) -> Any:
    raw, headers = signed(event, nonce=nonce or uuid.uuid4().hex)
    return c.post(EVENTS, content=raw, headers=headers)


def dm(sender: str, text: str) -> dict[str, Any]:
    return message(sender=sender, text=text, chat_id=DM, message_id=f"om_{uuid.uuid4().hex}")


def press(
    operator: str,
    value: Mapping[str, str],
    *,
    option: str = "",
    event_id: str | None = None,
) -> dict[str, Any]:
    """A `card.action.trigger` callback, schema 2.0, as Lark's server SDK parses one
    (`lark_oapi/event/callback/model/p2_card_action_trigger.py`): who pressed, the control's
    value and chosen option, and the card's message."""
    action: dict[str, Any] = {"value": dict(value), "tag": "select_static" if option else "button"}
    if option:
        action["option"] = option
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id or f"ev_{uuid.uuid4().hex}",
            "token": VERIFICATION_TOKEN,
            "create_time": str(int(time.time() * 1_000_000)),
            "event_type": "card.action.trigger",
            "tenant_key": "tenant-0001",
            "app_id": APP_ID,
        },
        "event": {
            "operator": {"tenant_key": "tenant-0001", "user_id": "", "open_id": operator},
            "token": "c-card-update-token",
            "action": action,
            "host": "im_message",
            "context": {"open_message_id": CARD_MESSAGE, "open_chat_id": DM},
        },
    }


def card_values(world: World) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str]]]:
    """The approve value, the reject value and the reject options of the one card posted."""
    [card] = [one[3] for one in world.lark.posted() if one[3] is not None]
    approve, reject = card["elements"][1]["actions"]
    options = [(one["value"], one["text"]["content"]) for one in reject["options"]]
    return approve["value"], reject["value"], options


def the_promotion(world: World) -> SuspendedAction:
    [only] = world.store.rows.values()
    return only


# ============================================================================ admission


def _held(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_someone",
        grants=tuple(Grant(capability=Capability(value=one), scope=WHOLE) for one in capabilities),
    )


def _held_values(reach: EntitlementSet) -> set[str]:
    return {one.capability.value for one in reach.grants}


def test_a_card_press_on_lark_carries_approve_and_a_message_there_does_not() -> None:
    """The security decision of this package, both directions. A press is a binding's read and
    `approve`, from the presser's own grants and nothing wider: never write, invoke or admin. A
    message on the same channel keeps a binding's read alone. Delete this and either a card cannot
    decide anything, or a message typed in Lark carries the approval its sender holds."""
    held = _held("read:x", "write:y", "invoke:z", "approve:v", "admin:w")
    assert _held_values(admit_card_press(held, Channel.LARK, switched_on=True)) == {
        "read:x",
        "approve:v",
    }
    assert _held_values(admit(held, Channel.LARK, Assurance.BOUND)) == {"read:x"}
    assert _held_values(admit_card_press(_held("read:x"), Channel.LARK, switched_on=True)) == {
        "read:x"
    }


@pytest.mark.parametrize(
    "channel",
    [
        Channel.WHATSAPP,
        Channel.EMAIL,
        Channel.WEBHOOK,
        Channel.SLACK,
        Channel.TELEGRAM,
        Channel.TEAMS,
        Channel.WIDGET,
    ],
)
def test_a_press_on_a_channel_that_carries_no_approval_admits_what_a_message_does(
    channel: Channel,
) -> None:
    """The channel's ceiling still bounds a press. Delete this and a button on WhatsApp, Slack or
    Teams decides an approval their ceilings refuse, which each of those modules argues against."""
    held = _held("read:x", "approve:v")
    pressed = admit_card_press(held, channel, switched_on=True)
    assert pressed == admit(held, channel, Assurance.BOUND)
    assert "approve:v" not in _held_values(pressed)


def test_a_card_press_carries_approve_only_while_the_install_s_switch_is_on() -> None:
    """Needs-rupash 117. The product cannot see whether a Lark sign-in had a second factor, so a
    press carries `approve` only while the install's Approve from Lark cards switch is on; off, it
    is admitted exactly what a message is. Delete this and a card approves on every install,
    including the ones whose Lark signs people in with a password alone."""
    held = _held("read:x", "approve:v")
    off = admit_card_press(held, Channel.LARK, switched_on=False)
    assert off == admit(held, Channel.LARK, Assurance.BOUND)
    assert _held_values(off) == {"read:x"}
    assert _held_values(admit_card_press(held, Channel.LARK, switched_on=True)) == {
        "read:x",
        "approve:v",
    }


def test_the_switch_ships_off_and_only_the_word_on_turns_it_on() -> None:
    """Read through `value_of`, saved value first, and compared with the one word that switches it
    on. Delete this and the default changes, or a typo in a saved row lets every card approve."""
    from brain.approval_cards import APPROVE_FROM_CARDS, cards_may_approve
    from brain.install import BY_NAME

    assert BY_NAME[APPROVE_FROM_CARDS].default == "off"
    assert cards_may_approve(env={}, saved={}) is False
    assert cards_may_approve(env={}, saved={APPROVE_FROM_CARDS: "on"}) is True
    assert cards_may_approve(env={APPROVE_FROM_CARDS: "on"}, saved={}) is True
    assert cards_may_approve(env={APPROVE_FROM_CARDS: "on"}, saved={APPROVE_FROM_CARDS: "off"}) is (
        False
    )
    for nobody_meant in ("yes", "On", "true", "1"):
        assert cards_may_approve(env={}, saved={APPROVE_FROM_CARDS: nobody_meant}) is False


def test_the_switch_is_changed_on_settings_as_on_or_off_and_says_why_it_is_off() -> None:
    """Changed through the Settings screen's own audited write, which judges a value before it is
    saved: on or off and nothing else. Its row says, in plain words, that a press rests on Lark's
    own sign-in and carries no second factor, and to switch it on only where Lark requires
    two-step verification. Delete this and the switch is saved as anything, or turned on by
    somebody nothing told what it gives up."""
    from brain.approval_cards import APPROVE_FROM_CARDS
    from brain.console.configuration import (
        EDITABLE_SETTINGS,
        LABELS,
        SECTION_OF,
        Section,
        row_for,
        setting_problem,
    )
    from brain.install import BY_NAME

    assert APPROVE_FROM_CARDS in EDITABLE_SETTINGS
    assert SECTION_OF[APPROVE_FROM_CARDS] is Section.LARK
    assert LABELS[APPROVE_FROM_CARDS] == "Approve from Lark cards"
    assert setting_problem(APPROVE_FROM_CARDS, "on") == ""
    assert setting_problem(APPROVE_FROM_CARDS, "off") == ""
    for refused in ("yes", "enabled", "ON"):
        assert setting_problem(APPROVE_FROM_CARDS, refused) != ""
    row = row_for(BY_NAME[APPROVE_FROM_CARDS], env={}, saved={})
    assert (row.value, row.editable) == ("off", True)
    for words in ("Lark's own sign-in", "no second factor", "two-step verification"):
        assert words in row.meaning


def test_a_card_is_offered_only_on_a_channel_that_carries_approvals_and_cards() -> None:
    """Lark carries both; the webhook channel and WhatsApp neither. Delete this and a card is
    offered where no press could ever be honoured."""
    assert carries_cards(Channel.LARK)
    assert not carries_cards(Channel.WEBHOOK)
    assert not carries_cards(Channel.WHATSAPP)


# ======================================================================== the text path


@pytest.mark.parametrize(
    ("said", "decides"),
    [
        ("approve", True),
        ("Approve.", True),
        ("/approve promotion.abc", True),
        ("reject it, wrong file", True),
        ("approvals", True),
        ("approved vendors?", False),
        ("what is the approval status of the handover document for maintenance today", False),
        ("please approve", False),
        ("", False),
    ],
)
def test_a_decision_word_is_recognised_and_a_question_or_a_sentence_is_not(
    said: str, decides: bool
) -> None:
    """Delete this and either a question opening with approve is never answered, or "approve" is
    answered as a question by the model, which says nothing about where approvals are decided."""
    assert is_decision_reply(said) is decides


@dataclass
class Answerer:
    """A `ChannelAnswerer` that records being asked, and answers nothing."""

    asked: list[str] = field(default_factory=list)

    async def answer(self, inbound: Inbound, **_: Any) -> Sequence[Any]:
        self.asked.append(inbound.event.text)
        return ()


class BoundToWide:
    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        return Binding(
            channel=channel,
            identity_hash=digest,
            principal_id="u_wide",
            bound_at=datetime(2019, 3, 4, 9, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize("channel", [Channel.WHATSAPP, Channel.WEBHOOK, Channel.EMAIL])
def test_approve_typed_on_another_channel_is_told_where_to_decide_and_reaches_no_answerer(
    channel: Channel,
) -> None:
    """M10.7.1 on the channels that are not Lark: the words never reach the gate's answerer, which
    is the only thing a message can reach, and the sender is told where approvals are decided. The
    sibling below proves a question still goes to the answerer. Delete this and "approve" on
    WhatsApp is answered as a question, and the approver believes they approved something."""
    event = ChannelEvent(
        channel=channel,
        external_id="m-1",
        channel_identity="+440000000000",
        text="approve",
        received_at=datetime(2999, 1, 1, tzinfo=UTC),
    )
    receipt = Receipt(
        kind=ReceiptKind.ACCEPTED,
        inbound=Inbound(event=event, address=from_mention(event.text)),
        reply_to="sender-1",
    )
    answerer = Answerer()
    replies = asyncio.run(
        reply_for(
            receipt,
            record=fresh_record(channel),
            bindings=BoundToWide(),
            answerer=answerer,
            now=datetime(2999, 1, 1, tzinfo=UTC),
        )
    )
    assert replies is not None
    assert [(one.to, one.text) for one in replies] == [("sender-1", DECIDE_WHERE_TOLD)]
    assert answerer.asked == []

    question = ChannelEvent(
        channel=channel,
        external_id="m-2",
        channel_identity="+440000000000",
        text="what is waiting on me",
        received_at=datetime(2999, 1, 1, tzinfo=UTC),
    )
    asked = Receipt(
        kind=ReceiptKind.ACCEPTED,
        inbound=Inbound(event=question, address=from_mention(question.text)),
        reply_to="sender-1",
    )
    asyncio.run(
        reply_for(
            asked,
            record=fresh_record(channel),
            bindings=BoundToWide(),
            answerer=answerer,
            now=datetime(2999, 1, 1, tzinfo=UTC),
        )
    )
    assert answerer.asked == ["what is waiting on me"]


# ======================================================================== the offer


def test_approve_typed_in_lark_decides_nothing_says_where_and_offers_the_approver_one_card(
    client: TestClient, world: World
) -> None:
    """M10.7.1 and M10.2.3 in Lark. The sentence first, with the install's Approvals page, then one
    card in the same private chat whose controls carry the suspension, its digest and whom it was
    built for, and the four reasons the console offers for a rejection. Nothing is decided and
    nothing reaches the ledger. Delete this and a typed approve on Lark either decides or is
    answered by the model, and the card the approver needs never arrives."""
    assert post(client, dm(WIDE, "approve")).status_code == 200
    posted = world.lark.posted()
    assert [(kind, where) for kind, where, _, _ in posted] == [("chat_id", DM), ("chat_id", DM)]
    assert posted[0][2] == f"{DECIDE_WHERE_TOLD} Open Approvals: {ORIGIN}/approvals"
    approve, reject, options = card_values(world)
    promotion = the_promotion(world)
    assert approve == {
        "suspension_id": promotion.id,
        "action_digest": promotion.action_digest,
        "decision": "approved",
        "rendered_for": "u_wide",
    }
    assert reject == {**approve, "decision": "rejected"}
    assert [value for value, _ in options] == [one.value for one in RejectionReason]
    assert "Site handover" in posted[1][2]
    assert promotion.state is ApprovalState.PENDING
    assert list(world.store.ledger.entries) == []


def test_a_person_who_may_not_decide_is_told_the_same_sentence_and_offered_no_card(
    client: TestClient, world: World
) -> None:
    """The sentence is one for everybody, so asking cannot learn whether anything waits, and a card
    goes only to somebody the Approvals screen would offer it: never to a holder of nothing, never
    to the person who asked for the promotion. Delete this and a card reaches somebody who cannot
    decide it, or the sentence itself says whether an approval exists."""
    post(client, dm(NARROW, "approve"))
    post(client, dm(OPEN_IDS["u_prefix"], "approve"))
    told = f"{DECIDE_WHERE_TOLD} Open Approvals: {ORIGIN}/approvals"
    assert [(where, text, card) for _, where, text, card in world.lark.posted()] == [
        (DM, told, None),
        (DM, told, None),
    ]


def test_in_a_group_the_sentence_and_the_card_go_to_the_sender_alone_and_never_the_room(
    client: TestClient, world: World
) -> None:
    """M10.7.4's last clause: a card is offered only where approvals are allowed, which is a chat
    its reader alone reads with the bot. Delete this and an approval card is posted to a group,
    where anybody present can see what it asks and press it."""
    event = message(
        sender=WIDE,
        text="@_user_1 approve",
        chat_id=GROUP,
        chat_type="group",
        message_id=f"om_{uuid.uuid4().hex}",
        mentions=[mention(BOT_OPEN_ID)],
    )
    post(client, event)
    posted = world.lark.posted()
    assert [(kind, where) for kind, where, _, _ in posted] == [("open_id", WIDE), ("open_id", WIDE)]
    assert posted[1][3] is not None


# ======================================================================== the press


def test_a_press_by_the_approver_decides_through_the_route_and_patches_the_card(
    client: TestClient, world: World
) -> None:
    """M10.2.3 and M10.2.4. The press is decided by `take_decision` as the bound approver: the row
    is approved under their name and the ledger holds one approval entry. Lark is answered with a
    toast, and after the answer the card is replaced in its own message by one with nothing to
    press saying what was decided. Delete this and a card press is either not a decision at all or
    a decision the card goes on offering."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    answered = post(client, press(WIDE, approve))
    assert answered.status_code == 200
    assert answered.json() == {
        "toast": {"type": "success", "content": DECIDED_TOLD[ApprovalState.APPROVED]}
    }
    decided = the_promotion(world)
    assert (decided.state, decided.decided_by) == (ApprovalState.APPROVED, "u_wide")
    [entry] = world.store.ledger.entries
    assert (entry.actor_id, entry.details["verdict"]) == ("u_wide", "approved")
    [(where, card)] = world.lark.edits()
    assert where == CARD_MESSAGE
    assert card["config"]["update_multi"] is True
    assert [one["tag"] for one in card["elements"]] == ["div"]
    assert card["elements"][0]["text"]["content"].endswith(
        "Decided: approved. Nothing is left to do on this card."
    )


def test_a_rejection_on_the_card_carries_the_reason_chosen_to_the_ledger(
    client: TestClient, world: World
) -> None:
    """A rejection names its reason, and the card's reject control is the four reasons. Delete
    this and a card rejects with a reason nobody gave, or cannot reject at all."""
    post(client, dm(WIDE, "approve"))
    _, reject, _ = card_values(world)
    answered = post(client, press(WIDE, reject, option="needs_more_detail"))
    assert answered.json()["toast"]["content"] == DECIDED_TOLD[ApprovalState.REJECTED]
    [entry] = world.store.ledger.entries
    assert (entry.details["verdict"], entry.details["reason_code"]) == (
        "rejected",
        "needs_more_detail",
    )


@pytest.mark.parametrize("option", ["", "because I said so"])
def test_a_rejection_with_no_reason_it_offered_decides_nothing(
    client: TestClient, world: World, option: str
) -> None:
    """Delete this and a press with no option, or one no card offered, reaches the route."""
    post(client, dm(WIDE, "approve"))
    _, reject, _ = card_values(world)
    answered = post(client, press(WIDE, reject, option=option))
    assert answered.json()["toast"]["content"] == PRESS_REFUSED_TOLD
    assert the_promotion(world).state is ApprovalState.PENDING


def test_a_press_by_another_bound_person_decides_nothing_and_leaves_their_copy_alone(
    client: TestClient, world: World
) -> None:
    """The card was built for `u_wide`; `u_narrow` pressing it, in a group or on a forwarded copy,
    is answered with the one refusal and their card is not touched. Delete this and whoever can see
    a card can decide it."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    answered = post(client, press(NARROW, approve))
    assert answered.json() == {"toast": {"type": "info", "content": PRESS_REFUSED_TOLD}}
    assert the_promotion(world).state is ApprovalState.PENDING
    assert list(world.store.ledger.entries) == []
    assert world.lark.edits() == []


def test_a_press_by_somebody_bound_to_nobody_decides_nothing(
    client: TestClient, world: World
) -> None:
    """Delete this and an unbound Lark account's press is decided as whoever the card names."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    answered = post(client, press("ou_stranger00000000000000000001", approve))
    assert answered.json()["toast"]["content"] == PRESS_REFUSED_TOLD
    assert the_promotion(world).state is ApprovalState.PENDING


def test_a_replayed_press_is_refused_by_the_claim_and_decides_once(
    client: TestClient, world: World
) -> None:
    """The same signed callback posted twice is one press. Delete this and a captured request
    replayed inside the signature's window is a second decision attempt."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    once = press(WIDE, approve)
    raw, headers = signed(once, nonce="nonce-replayed")
    first = client.post(EVENTS, content=raw, headers=headers)
    again = client.post(EVENTS, content=raw, headers=headers)
    assert first.json()["toast"]["type"] == "success"
    assert again.json() == {"status": "redelivered", "reply": None}
    assert len(list(world.store.ledger.entries)) == 1
    assert len(world.lark.edits()) == 1


def test_a_press_after_the_approval_was_decided_in_the_console_decides_nothing_and_closes_the_card(
    client: TestClient, world: World
) -> None:
    """`u_elsewhere` rejects it on the Approvals screen, through the route's own function at the
    console's admitted reach; `u_wide` then presses their card. Nothing more is decided, the row
    keeps the console's decision, and the card is replaced in the answer by one with nothing to
    press, saying nothing of who decided or how. Delete this and a stale card decides twice, or
    tells its reader what somebody else did."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    promotion = the_promotion(world)
    reach = admit(
        EntitlementSet(principal_id="u_elsewhere", grants=GRANTS["u_elsewhere"]),
        Channel.CONSOLE,
        Assurance.STRONG,
    )
    asyncio.run(
        take_decision(
            world.store,
            promotion.id,
            reach,
            DecisionAsked(
                verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.NO_LONGER_NEEDED
            ),
            trace_id="trace_console",
            now=datetime.now(UTC),
        )
    )
    answered = post(client, press(WIDE, approve))
    assert answered.json()["toast"] == {"type": "info", "content": PRESS_REFUSED_TOLD}
    assert answered.json()["card"]["data"]["elements"] == [
        {"tag": "div", "text": {"tag": "plain_text", "content": CLOSED_TOLD}}
    ]
    decided = the_promotion(world)
    assert (decided.state, decided.decided_by) == (ApprovalState.REJECTED, "u_elsewhere")
    assert len(list(world.store.ledger.entries)) == 1
    assert world.lark.edits() == []


def test_a_press_naming_another_action_or_carrying_more_than_a_card_does_decides_nothing(
    client: TestClient, world: World
) -> None:
    """The digest binds a press to the action its card was built for, and a value is exactly the
    four identifiers a card writes. Delete this and an amended action is approved by a card for
    the old one, or a value somebody composed is guessed at."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    for value in ({**approve, "action_digest": "0" * 64}, {**approve, "note": "x"}):
        answered = post(client, press(WIDE, value))
        assert answered.json()["toast"]["content"] == PRESS_REFUSED_TOLD
    assert the_promotion(world).state is ApprovalState.PENDING


def test_a_refused_patch_sends_the_text_fallback_to_the_approver_s_own_chat(
    client: TestClient, world: World
) -> None:
    """M10.2.4's fallback, in the case it is for: Lark refused the replacement, so the approver is
    told in their own chat that the card above is out of date. Delete this and a card Lark would
    not update goes on showing an open decision with nothing saying otherwise."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    world.lark.refuse_edits = True
    before = len(world.lark.posted())
    post(client, press(WIDE, approve))
    promotion = the_promotion(world)
    assert len(world.lark.edits()) == 1
    assert [(kind, where, text) for kind, where, text, _ in world.lark.posted()[before:]] == [
        ("open_id", WIDE, FALLBACK_TEMPLATE.format(suspension=promotion.id, state="approved"))
    ]


def test_with_the_close_window_full_the_decision_stands_and_nothing_more_is_sent(
    client: TestClient, world: World
) -> None:
    """The close half of the card ceiling is the budget both the patch and its fallback draw on,
    so a full window sends neither and the decision is still taken. Delete this and the card
    ceiling is spent past the vendor's limit exactly when approvals are busiest."""
    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)
    limit = card_limit(CardCall.CLOSE)
    now = datetime.now(UTC)
    world.windows.state = LimiterState(
        windows={limit.key: WindowState(hits=tuple(now for _ in range(limit.limit)))}
    )
    sent = len(world.lark.sent)
    answered = post(client, press(WIDE, approve))
    assert answered.json()["toast"]["type"] == "success"
    assert the_promotion(world).state is ApprovalState.APPROVED
    assert len(world.lark.sent) == sent


def test_with_the_switch_off_the_approver_is_sent_the_card_with_no_button_and_the_console_named(
    client: TestClient, world: World
) -> None:
    """The positive half of the switch being off: the approver still gets the card, its body as
    the Approvals screen shows them, with no control to press and a last line naming the console's
    Approvals page. Delete this and switching approvals off also stops anybody being told one is
    waiting."""
    world.switched_on = False
    client.app.state.approve_from_cards = False  # type: ignore[attr-defined]
    post(client, dm(WIDE, "approve"))
    posted = world.lark.posted()
    assert [(kind, where) for kind, where, _, _ in posted] == [("chat_id", DM), ("chat_id", DM)]
    card = posted[1][3]
    assert card is not None
    assert [one["tag"] for one in card["elements"]] == ["div"]
    text = posted[1][2]
    assert "Site handover" in text
    assert text.endswith(f"Decide this in the console: {ORIGIN}/approvals")
    assert "Approve" not in json.dumps(card)


def test_with_the_switch_off_a_press_decides_nothing_and_never_reaches_the_route(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card sent while the switch was on, pressed after it was turned off: the presser is told to
    decide in the console, nothing is decided, and the Approvals route's `take_decision` is never
    asked. Delete this and turning the switch off leaves every card already sent able to approve."""
    import brain.approval_cards
    from brain.approval_cards import DECIDE_IN_THE_CONSOLE_TOLD

    post(client, dm(WIDE, "approve"))
    approve, _, _ = card_values(world)

    async def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("take_decision was reached from a card while the switch was off")

    monkeypatch.setattr(brain.approval_cards, "take_decision", never)
    client.app.state.approve_from_cards = False  # type: ignore[attr-defined]
    answered = post(client, press(WIDE, approve))
    assert answered.json() == {"toast": {"type": "info", "content": DECIDE_IN_THE_CONSOLE_TOLD}}
    assert the_promotion(world).state is ApprovalState.PENDING
    assert list(world.store.ledger.entries) == []
    assert world.lark.edits() == []


# ======================================================================== the pieces


def test_an_agent_s_action_is_not_offered_on_a_card_so_nothing_on_a_card_is_taken_over() -> None:
    """`A_CARD_CARRIES_NO_AGENT_ACTION_SO_NOTHING_ON_IT_IS_TAKEN_OVER`, both halves. An approver
    holding an agent action's own capability is offered it in the console, which is where Take over
    is; the same approver's press reach on Lark is not, and every card Lark is offered is a
    promotion, which offers no takeover. Delete this and a press admitted an action's own verb one
    day sends agents' actions to Lark with no Take over on them and nobody told."""
    from brain.approval_routes import shown_card
    from tests.unit.test_approval_decisions import WRITE_STATUS, a_suspension

    now = datetime.now(UTC)
    held = EntitlementSet(
        principal_id="u_wide",
        grants=(
            Grant(capability=Capability(value=WRITE_STATUS), scope=WHOLE),
            APPROVE,
        ),
    )
    agents = a_suspension("m_1")
    in_console = shown_card(agents, held, now)
    on_a_card = shown_card(agents, admit_card_press(held, Channel.LARK, switched_on=True), now)
    promotion = shown_card(
        a_promotion("u_prefix"), admit_card_press(held, Channel.LARK, switched_on=True), now
    )

    assert in_console is not None and in_console.may_take_over is True
    assert on_a_card is None
    assert promotion is not None and promotion.may_take_over is False


def test_the_reasons_a_card_offers_are_the_console_s_own_words() -> None:
    """Held to `REJECTION_REASONS` in the console's Approvals query, so a reason reads the same on
    a phone in Lark and on the screen. Delete this and the two drift apart one edit at a time."""
    source = (ROOT / "console" / "src" / "pages" / "approvalsQuery.ts").read_text(encoding="utf-8")
    block = source[source.index("REJECTION_REASONS") :]
    block = block[block.index("{") + 1 : block.index("}")]
    console = dict(re.findall(r'(\w+):\s*"([^"]+)"', block))
    assert console == {reason.value: words for reason, words in REJECTION_WORDS.items()}


def test_a_signed_card_press_is_read_as_a_press_keyed_on_its_own_callback() -> None:
    """The wire reads a press into its value, its option and the card's message, beside an event
    keyed on the callback's id and never on a message's, so the claim refuses a replayed press and
    a press never collides with a message. Delete this and presses reach the route unread."""
    raw, headers = signed(press(WIDE, {"a": "b"}, option="x", event_id="ev_42"))
    secret = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    opened = WIRE.verify(Arrived(headers=headers, body=raw), secret, datetime.now(UTC))
    read = WIRE.read(opened)
    assert read.press is not None
    assert (read.press.value, read.press.option, read.press.message_id) == (
        {"a": "b"},
        "x",
        CARD_MESSAGE,
    )
    assert (read.event.external_id, read.event.channel_identity) == ("press.ev_42", WIDE)
    assert read.reply_to == f"user:{WIDE}" and read.conversation is None
    anonymous = press(WIDE, {"a": "b"})
    del anonymous["event"]["context"]
    raw, headers = signed(anonymous)
    with pytest.raises(ValueError, match="names the card"):
        WIRE.read(WIRE.verify(Arrived(headers=headers, body=raw), secret, datetime.now(UTC)))


def test_an_approval_card_is_never_posted_as_an_aside_in_a_room() -> None:
    """A card with controls on it posted as a group aside is a control in a room. Delete this and
    `card_request` builds one for any address it is handed."""
    secret = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    tenant = {"app_id": APP_ID, "platform": "larksuite.com"}
    actions = (CardAction(text="Approve", value={"a": "b"}),)
    made = WIRE.card_request(
        to=f"user:{WIDE}", text="t", actions=actions, secret=secret, tenant=tenant
    )
    assert json.loads(made.body)["msg_type"] == "interactive"
    with pytest.raises(ValueError, match="posts a card to"):
        WIRE.card_request(
            to=f"aside:{GROUP}:{WIDE}", text="t", actions=actions, secret=secret, tenant=tenant
        )


def test_a_decided_card_is_patched_within_the_close_window_and_a_full_window_raises() -> None:
    """`close_admitted` with the window's decision made outside: admitted, the card is disarmed and
    patched; refused, `CardStaleError` carries the disarmed card and the wait. And a decided body
    is refused for a card still armed. Delete this and the shared window's answer can be ignored."""
    from brain.approval_cards import built, card_payload
    from brain.console.approvals import card as shown_for

    promotion = a_promotion("u_prefix")
    reach = admit_card_press(
        EntitlementSet(principal_id="u_wide", grants=(APPROVE,)), Channel.LARK, switched_on=True
    )
    now = datetime.now(UTC)
    shown = shown_for(promotion, reach, now)
    assert shown is not None
    card = built(promotion, shown, reach=reach, channel=Channel.LARK)
    assert card.payload == card_payload(shown)
    with pytest.raises(CardRefusedError, match="not closed"):
        render_decided(card)
    limit = card_limit(CardCall.CLOSE)
    admitted = HeldCardWindows()
    plan = close_admitted(
        card,
        state=ApprovalState.APPROVED,
        decision=asyncio.run(admitted.spend(CardCall.CLOSE, now)),
        capabilities=adapter_for(Channel.LARK).capabilities(),
    )
    assert plan.outcome is PatchOutcome.PATCHED and plan.card.armed is False
    assert render_decided(plan.card).endswith(
        "Decided: approved. Nothing is left to do on this card."
    )
    full = HeldCardWindows(
        LimiterState(windows={limit.key: WindowState(hits=tuple(now for _ in range(limit.limit)))})
    )
    with pytest.raises(CardStaleError) as raised:
        close_admitted(
            card,
            state=ApprovalState.APPROVED,
            decision=asyncio.run(full.spend(CardCall.CLOSE, now)),
            capabilities=adapter_for(Channel.LARK).capabilities(),
        )
    assert raised.value.card.armed is False and raised.value.retry_after_seconds > 0


def test_a_card_replacement_goes_by_the_edit_door_of_the_one_transport() -> None:
    """A PATCH is an effect like a POST and leaves by the same keyed `send`, and the sender's
    `edit` makes it with its body. Delete this and a replacement is refused by the transport, or
    made without the card it carries."""
    from brain.channel_routes import HttpsTransport
    from brain.ops.outbox_store import SendResult

    @dataclass
    class Sender:
        seen: list[tuple[str, bytes]] = field(default_factory=list)

        def _answer(self, how: str, request: Any) -> SendResult:
            self.seen.append((how, request.body))
            return SendResult(
                status=200, body=json.dumps({"code": 0, "tenant_access_token": "t"}).encode()
            )

        def send(self, request: Any) -> SendResult:
            return self._answer("send", request)

        def edit(self, request: Any) -> SendResult:
            return self._answer("edit", request)

        def mint(self, request: Any) -> SendResult:
            return self._answer("mint", request)

        def read(self, request: Any) -> SendResult:
            return self._answer("read", request)

    class Public:
        def resolve(self, host: str) -> list[str]:
            del host
            return ["8.8.8.8"]

    sender = Sender()
    transport = HttpsTransport(resolver=Public(), sender=sender)  # type: ignore[arg-type]
    secret = LarkSecret(
        app_secret=APP_SECRET, encrypt_key=ENCRYPT_KEY, verification_token=VERIFICATION_TOKEN
    ).kept()
    request = WIRE.request_for(
        to=WIRE.edit_address(CARD_MESSAGE),
        text="closed",
        secret=secret,
        tenant={"app_id": APP_ID, "platform": "larksuite.com"},
        now=datetime.now(UTC),
    )
    assert request.method == "PATCH" and request.url.endswith(f"/im/v1/messages/{CARD_MESSAGE}")
    transport.send(request)
    assert [how for how, _ in sender.seen] == ["mint", "edit"]
    assert (
        json.loads(json.loads(sender.seen[1][1])["content"])["elements"][0]["text"]["content"]
        == "closed"
    )
    with pytest.raises(ValueError):
        transport.read(request)
