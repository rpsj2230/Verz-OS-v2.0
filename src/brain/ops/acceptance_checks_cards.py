"""The install acceptance checks for approval cards in Lark, and for what a chat may not decide.

Each check drives the install's own events route, `POST /api/v1/channels/lark/events`, on the Lark
app `brain.ops.acceptance_checks_chat.lark_app` sets up over the check's rolled-back transaction,
with the route's own wiring choosing every store: the chat bindings CH2 keeps, the directory, the
gate's entitlement store, and `gate.suspension` through `brain.gate.suspension_store`, which is
where the Approvals screen reads and decides. What is proved is the install's route: the wire
reading a signed card callback, the claim, `brain.approval_cards`, and `take_decision`, the one
function the Approvals route decides with.

**The approvals are real promotions, raised as the promotion route raises them.** A steward in
acceptance_a adds a document, verifies it and asks for it to be company-wide, through the
lifecycle checks' own steps (`brain.ops.acceptance_checks_lifecycle`), so each card is for a
suspension requiring `approve:knowledge.visibility` over acceptance_a, which the approvers hold
and the bystander does not. Rejected: a suspension written by hand, which would prove the cards
over a row no route writes.

**What stays in memory is the chat checks' list, and the card windows.** The Lark app's secret,
its transport and the operation ledger are the chat checks', for their reason
(`NOTHING_THE_CHECK_SENDS_LEAVES_THE_PROCESS`): the transport keeps every request, answers a send
with Lark's documented success and, when a check asks it to, a card replacement with a refusal,
so no real chat hears anything. The card ceiling's windows are `HeldCardWindows` on the
application, because a check may not touch a key another caller uses
(`WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`), and the install's are shared.

**Both states of the install's Approve from Lark cards switch are run, on the check's own
application** (needs-rupash 117). The switch ships off and is the owner's to turn on, so the checks
state it on their application rather than reading or writing the install's: `state.approve_from_
cards`, which `brain.approval_cards.ApprovalCards.of` prefers to the installation value exactly so
that a check or a test can say which state it is exercising. Off, a card is sent with nothing to
press and names the console, and a press decides nothing; on, what follows.

**The group and policy check reuses the room check whole.** M10.7.4's sentence is three clauses;
the first is what `a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone` proves, so it
is awaited as it stands rather than copied, then the ceiling is asked of the install's one send
step, and the card clause is the first check here, which names M10.7.4 as well.

Task ids: M10.2.3, M10.2.4, M10.7.1, M10.7.4
"""

from __future__ import annotations

import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _ledger
from brain.ops.acceptance_checks_chat import (
    SENT_ENVELOPE,
    _Lark,
    _LarkApp,
    a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone,
    bound,
    chat_id,
    lark_app,
    open_id,
    sealed,
)
from brain.ops.acceptance_checks_lifecycle import (
    REVIEW_AHEAD,
    _added,
    _as,
    _propose,
    _status,
    _verify,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.acceptance_checks_lifecycle import _Person

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 280

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the approvals are promotions raised through the lifecycle's own steps.
EVERY_CARD_IS_FOR_AN_APPROVAL_A_ROUTE_RAISED: Final = (
    "Each card is for a promotion a steward in acceptance_a asked for through the promotion "
    "route's own steps, so it requires approve:knowledge.visibility there, is kept in "
    "gate.suspension and is decided through the Approvals route's take_decision."
)

# ------------------------------------------------------------------------ the figures
#: The message id Lark answers every card send with in the check's transport (`SENT_ENVELOPE`),
#: which is the id a press on that card names and a replacement of it is addressed to.
CARD_MESSAGE: Final = "om_acceptance"

#: What the check's Lark answers a card replacement with when a check asks it to refuse one: a
#: refusal inside a 200, which is where Lark refuses and what the wire judges by its code.
EDIT_REFUSED: Final = {"code": 230002, "msg": "Bot is not in the chat"}

#: A sha256 hexdigest, which an action digest is.
_DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")


# --------------------------------------------------------------------- Lark in memory
@dataclass
class _CardLark(_Lark):
    """The chat checks' Lark, answering a card replacement with a refusal when asked to."""

    refuse_edits: bool = False

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        refused = self.refuse_edits and request.method == "PATCH"
        return VendorAnswer(
            status=200, body=json.dumps(EDIT_REFUSED if refused else SENT_ENVELOPE).encode()
        )

    def posted(self) -> list[tuple[str, str, str, dict[str, Any] | None]]:
        """Every message and card posted, as (to whom by, where, text, card), in order: Lark's
        `receive_id_type` and id for a chat message, or `reply` and the sender for the webhook."""
        found: list[tuple[str, str, str, dict[str, Any] | None]] = []
        for request in self.sent:
            if request.method != "POST":
                continue
            address = urlsplit(request.url)
            body = json.loads(request.body)
            if address.path.endswith("/im/v1/messages"):
                kind = parse_qs(address.query)["receive_id_type"][0]
                content = json.loads(body["content"])
                if body["msg_type"] == "interactive":
                    text = content["elements"][0]["text"]["content"]
                    found.append((kind, body["receive_id"], text, content))
                else:
                    found.append((kind, body["receive_id"], content["text"], None))
            elif "to" in body and "text" in body:
                found.append(("reply", body["to"], body["text"], None))
        return found

    def edits(self) -> list[tuple[str, str]]:
        """Every card replaced in place, as (its message id, the text it was replaced with)."""
        return [
            (
                urlsplit(one.url).path.rsplit("/", 1)[-1],
                json.loads(json.loads(one.body)["content"])["elements"][0]["text"]["content"],
            )
            for one in self.sent
            if one.method == "PATCH"
        ]


def press_event(
    *, app_id: str, token: str, operator: str, value: Mapping[str, str], option: str = ""
) -> dict[str, Any]:
    """A `card.action.trigger` callback, schema 2.0, as Lark's server SDK parses one
    (`larksuite/oapi-sdk-python`, `lark_oapi/event/callback/model/p2_card_action_trigger.py`): who
    pressed, the control's value and any option chosen, and the card's message."""
    action: dict[str, Any] = {"value": dict(value), "tag": "select_static" if option else "button"}
    if option:
        action["option"] = option
    return {
        "schema": "2.0",
        "header": {
            "event_id": f"ev_{secrets.token_hex(12)}",
            "token": token,
            "create_time": str(int(time.time() * 1_000_000)),
            "event_type": "card.action.trigger",
            "tenant_key": "acceptance",
            "app_id": app_id,
        },
        "event": {
            "operator": {"tenant_key": "acceptance", "user_id": "", "open_id": operator},
            "token": f"c-{secrets.token_hex(8)}",
            "action": action,
            "host": "im_message",
            "context": {"open_message_id": CARD_MESSAGE, "open_chat_id": chat_id()},
        },
    }


def lark_press(
    chat: _LarkApp, operator: str, value: Mapping[str, str], *, option: str = ""
) -> dict[str, Any]:
    """`press_event` for this check's Lark app."""
    return press_event(
        app_id=chat.app_id, token=chat.token, operator=operator, value=value, option=option
    )


async def _post_raw(
    chat: _LarkApp, path: str, raw: bytes, headers: Mapping[str, str]
) -> tuple[int, dict[str, Any]]:
    """One request to the install's events route; the status and the body it answered with."""
    import httpx

    transport = httpx.ASGITransport(app=chat.app)
    async with httpx.AsyncClient(transport=transport, base_url="https://acceptance.invalid") as c:
        answered = await c.post(path, content=raw, headers=dict(headers))
    body = answered.json() if answered.content else {}
    return answered.status_code, body if isinstance(body, dict) else {}


async def pressed(chat: _LarkApp, event: Mapping[str, Any]) -> dict[str, Any]:
    """A press sealed and signed as Lark sends one, posted; what the route answered Lark with."""
    from brain.ops.lark_connect import LARK_EVENTS_PATH

    raw, headers = sealed(event, chat.encrypt_key)
    status, body = await _post_raw(chat, LARK_EVENTS_PATH, raw, headers)
    if status != 200:
        raise CheckFailedError("a signed press was not accepted by the events address")
    return body


# ------------------------------------------------------------------------ the set-up
@dataclass
class _Desk:
    """One check's approvals: the chat, who is who, and their Lark accounts."""

    h: Harness
    chat: _LarkApp
    lark: _CardLark
    steward: str
    approver: str
    second: str
    bystander: str
    ids: dict[str, str] = field(default_factory=dict)

    async def says(self, principal: str, text: str, *, group: bool = False) -> list[Any]:
        """What one message from this person, in a new direct chat or a group naming the bot,
        was answered with."""
        before = len(self.lark.posted())
        conversation = chat_id()
        await self.chat.post(
            self.ids[principal], text, chat=conversation, group=group, to_bot=group
        )
        return [
            (kind, where.replace(conversation, "here"), text, card)
            for kind, where, text, card in self.lark.posted()[before:]
        ]

    async def promotion(self) -> tuple[str, str]:
        """A promotion the steward asked for: its suspension id and the document's id."""
        item = await _added(self.h, self.steward, self.h.word())
        asking = await _as(self.h, self.steward)
        if await _verify(self.h, asking, item, review_by=self.h.now + REVIEW_AHEAD) is None:
            raise CheckFailedError("the steward could not verify their own document")
        card = await _propose(self.h, asking, item)
        if card is None:
            raise CheckFailedError("a steward's verified document could not be asked for")
        return card, item

    async def asking(self) -> _Person:
        return await _as(self.h, self.steward)

    def switch(self, *, on: bool) -> None:
        """The Approve from Lark cards switch as this check's application reads it."""
        self.chat.app.state.approve_from_cards = on


async def desk(h: Harness) -> _Desk:
    """The cards' application over the check's transaction, and four bound reserved people."""
    from brain.approval_cards import HeldCardWindows
    from brain.gate.suspension_store import StoredSuspensions
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import PROMOTION_CAPABILITY

    await h.found_departments()
    approves = PROMOTION_CAPABILITY.value
    made = _Desk(
        h=h,
        chat=await lark_app(h),
        lark=_CardLark(),
        steward=h.principal(A, "cardsteward"),
        approver=h.principal(A, "cardapprover"),
        second=h.principal(A, "cardsecond"),
        bystander=h.principal(A, "cardbystander"),
    )
    await h.person(
        made.steward,
        department=A,
        grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value, approves),
    )
    await h.person(made.approver, department=A, grants=_in(A, approves))
    await h.person(made.second, department=A, grants=_in(A, approves))
    await h.person(made.bystander, department=A, grants=_in(A, *KNOWLEDGE_READS))
    made.chat.lark = made.lark
    state = made.chat.app.state
    state.channel_transport = made.lark
    state.suspensions = StoredSuspensions(h.sessions)
    state.card_windows = HeldCardWindows()
    made.switch(on=True)
    made.ids = {
        one: open_id() for one in (made.steward, made.approver, made.second, made.bystander)
    }
    await bound(made.chat, made.ids)
    return made


def _told() -> str:
    """What a decision word is answered with on this install."""
    from brain.approval_cards import approvals_link, where_to_decide

    return where_to_decide(approvals_link())


def _cards(answered: list[Any]) -> dict[str, tuple[dict[str, str], dict[str, str]]]:
    """The cards in a reply, by suspension: each one's approve and reject values."""
    found: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    for _, _, _, card in answered:
        if card is None or len(card["elements"]) < 2:
            # A message, or a card with nothing to press on it.
            continue
        approve, reject = card["elements"][1]["actions"]
        found[str(approve["value"]["suspension_id"])] = (approve["value"], reject["value"])
    return found


async def _decisions(h: Harness, suspension_id: str) -> list[tuple[str, Any, Any]]:
    """Who decided a suspension, the verdict and the reason, as its ledger entries say."""
    from brain.audit.record import subject

    return [
        (actor, details.get("verdict"), details.get("reason_code"))
        for actor, details in await _ledger(h, subject("leash", suspension_id))
    ]


# ------------------------------------------------------------------ 1. typed, never decided
@check(
    leaves=("M10.7.1", "M10.2.3", "M10.7.4"),
    sentence=(
        "Bound reserved people type approve: in Lark the approver of a waiting promotion is told "
        "where approvals are decided and sent its card in their own chat, never a group, with no "
        "button and the console named while approving from Lark is off, buttons once on; a "
        "bystander and the asker are told the same with no card; the webhook channel gets the "
        "sentence; nothing typed decides it."
    ),
)
async def typed_approve_decides_nothing_and_the_approver_gets_one_card(
    h: Harness,
) -> None:
    from brain.approval_cards import THE_APPROVALS_SCREEN, approvals_link
    from brain.channels.cards import DECIDE_IN_THE_CONSOLE
    from brain.gate.admission import admit_card_press
    from brain.gate.context import Channel
    from brain.gate.suspension_store import StoredSuspensions
    from brain.knowledge.promotion import PromotionStatus

    made = await desk(h)
    card, item = await made.promotion()
    told = _told()

    made.switch(on=False)
    noticed = await made.says(made.approver, "approve")
    made.switch(on=True)
    mine = await made.says(made.approver, "approve")
    for answer in (noticed, mine):
        if [(kind, where, text) for kind, where, text, _ in answer[:1]] != [
            ("chat_id", "here", told)
        ]:
            raise CheckFailedError(
                "an approver typing approve was not told where approvals are decided"
            )
        if [(kind, where) for kind, where, _, _ in answer] != [("chat_id", "here")] * 2 or [
            one[3] is not None for one in answer
        ] != [False, True]:
            raise CheckFailedError("the approver was not sent exactly one card, in their own chat")
    console = DECIDE_IN_THE_CONSOLE.format(where=approvals_link() or THE_APPROVALS_SCREEN)
    notice = noticed[1][3]
    if (
        notice is None
        or [one["tag"] for one in notice["elements"]] != ["div"]
        or not noticed[1][2].endswith(console)
    ):
        raise CheckFailedError("with Lark approvals off the card offered a button or no console")
    offered = _cards(mine)
    if list(offered) != [card]:
        raise CheckFailedError("the approver was not sent exactly one card, in their own chat")
    approve, reject = offered[card]
    reach = admit_card_press(await h.reach(made.approver), Channel.LARK, switched_on=True)
    stored = await StoredSuspensions(h.sessions).reading_as(reach, h.now).suspension(card)
    if (
        stored is None
        or approve
        != {
            "suspension_id": card,
            "action_digest": stored.action_digest,
            "decision": "approved",
            "rendered_for": made.approver,
        }
        or reject != {**approve, "decision": "rejected"}
        or not _DIGEST.match(approve["action_digest"])
    ):
        raise CheckFailedError("the card did not name its approval, its action and its approver")

    for somebody in (made.bystander, made.steward):
        if await made.says(somebody, "approve") != [("chat_id", "here", told, None)]:
            raise CheckFailedError("somebody who may not decide was sent more than the sentence")

    grouped = await made.says(made.approver, "approve", group=True)
    mine_alone = ("open_id", made.ids[made.approver])
    if not grouped or any((kind, where) != mine_alone for kind, where, _, _ in grouped):
        raise CheckFailedError("a group message about deciding was answered in the group")

    if await _webhook_says(made, "approve") != [told]:
        raise CheckFailedError("approve typed on the webhook channel was not told where to decide")

    if await _status(h, await made.asking(), item) is not PromotionStatus.WAITING:
        raise CheckFailedError("something typed in a chat decided the promotion")
    if await _decisions(h, card):
        raise CheckFailedError("something typed in a chat wrote an approval to the ledger")


async def _webhook_says(made: _Desk, text: str) -> list[str]:
    """The approver, bound on the webhook channel, sends `text`; the text of every reply."""
    from brain.api import API_PREFIX
    from brain.channel_routes import EVENTS_PATH
    from brain.channels.webhook import REPLY_URL, SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
    from brain.gate.context import Channel
    from brain.gate.ingress import identity_hash
    from brain.ops.channel_store import StoredChannels
    from brain.tables.identity import PrincipalIdentityRow

    h = made.h
    sender = f"acceptance-{h.run}-{secrets.token_hex(4)}"
    await StoredChannels(h.sessions).save(
        Channel.WEBHOOK,
        enabled=True,
        tenant={REPLY_URL: f"https://acceptance.invalid/{h.run}"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            channel=Channel.WEBHOOK.value,
            identity_hash=identity_hash(Channel.WEBHOOK, sender),
            principal_id=made.approver,
            bound_at=h.now,
        ),
    )
    body = json.dumps({"id": f"acceptance-{secrets.token_hex(8)}", "sender": sender, "text": text})
    raw = body.encode()
    stamp = str(int(time.time()))
    secret = str(made.chat.app.state.channel_secrets.value)
    headers = {TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(secret, stamp, raw)}
    before = len(made.lark.posted())
    path = API_PREFIX + EVENTS_PATH.format(name=Channel.WEBHOOK.value)
    status, _ = await _post_raw(made.chat, path, raw, headers)
    if status != 200:
        raise CheckFailedError("a signed message was not accepted on the webhook channel")
    return [text for kind, where, text, _ in made.lark.posted()[before:] if where == sender]


# ------------------------------------------------------------------ 2. pressed, and closed
@check(
    leaves=("M10.2.3", "M10.2.4"),
    sentence=(
        "Signed Lark card presses on three waiting promotions: the approver's decides nothing "
        "while approving from Lark is off; once on, a bystander's decides nothing, the approver's "
        "approves as them in the ledger and the card is replaced, a replay and a press after a "
        "console rejection decide nothing, and a rejection whose replacement Lark refuses is told "
        "in the approver's own chat."
    ),
)
async def a_card_press_decides_as_its_approver_alone_and_closes_the_card(h: Harness) -> None:
    from brain.approval_cards import (
        CLOSED_TOLD,
        DECIDE_IN_THE_CONSOLE_TOLD,
        DECIDED_TOLD,
        PRESS_REFUSED_TOLD,
    )
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        RejectionReason,
        take_decision,
    )
    from brain.channels.cards import FALLBACK_TEMPLATE
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.gate.leash import ApprovalState
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.lark_connect import LARK_EVENTS_PATH

    made = await desk(h)
    first, _ = await made.promotion()
    refused, _ = await made.promotion()
    elsewhere, _ = await made.promotion()
    offered = _cards(await made.says(made.approver, "approve"))
    if set(offered) != {first, refused, elsewhere}:
        raise CheckFailedError("the approver was not offered a card for each waiting promotion")
    approver = made.ids[made.approver]

    made.switch(on=False)
    answered = await pressed(made.chat, lark_press(made.chat, approver, offered[first][0]))
    if answered.get("toast", {}).get("content") != DECIDE_IN_THE_CONSOLE_TOLD or await _decisions(
        h, first
    ):
        raise CheckFailedError("a press decided an approval while approving from Lark was off")
    made.switch(on=True)

    by_somebody = lark_press(made.chat, made.ids[made.bystander], offered[first][0])
    answered = await pressed(made.chat, by_somebody)
    if answered.get("toast", {}).get("content") != PRESS_REFUSED_TOLD or await _decisions(h, first):
        raise CheckFailedError("a press by somebody the card was not built for decided it")

    once = lark_press(made.chat, approver, offered[first][0])
    raw, headers = sealed(once, made.chat.encrypt_key)
    status, answered = await _post_raw(made.chat, LARK_EVENTS_PATH, raw, headers)
    if status != 200 or answered.get("toast") != {
        "type": "success",
        "content": DECIDED_TOLD[ApprovalState.APPROVED],
    }:
        raise CheckFailedError("the approver's press was not answered as their approval")
    if await _decisions(h, first) != [(made.approver, "approved", None)]:
        raise CheckFailedError("the approver's press was not in the ledger as their approval")
    if made.lark.edits() != [(CARD_MESSAGE, _decided_body(made.lark, first, "approved"))]:
        raise CheckFailedError("the decided card was not replaced by one saying what was decided")
    status, again = await _post_raw(made.chat, LARK_EVENTS_PATH, raw, headers)
    if again.get("status") != "redelivered" or len(await _decisions(h, first)) != 1:
        raise CheckFailedError("a replayed press was not refused by the claim")

    console = admit(await h.reach(made.second), Channel.CONSOLE, Assurance.STRONG)
    await take_decision(
        StoredSuspensions(h.sessions),
        elsewhere,
        console,
        DecisionAsked(
            verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.NO_LONGER_NEEDED
        ),
        trace_id=h.trace_id,
        now=datetime.now(UTC),
    )
    answered = await pressed(made.chat, lark_press(made.chat, approver, offered[elsewhere][0]))
    closed = answered.get("card", {}).get("data", {}).get("elements")
    if answered.get("toast", {}).get("content") != PRESS_REFUSED_TOLD or closed != [
        {"tag": "div", "text": {"tag": "plain_text", "content": CLOSED_TOLD}}
    ]:
        raise CheckFailedError("a press after a decision in the console was not refused and closed")
    if await _decisions(h, elsewhere) != [(made.second, "rejected", "no_longer_needed")]:
        raise CheckFailedError("a press after a decision in the console changed that decision")

    made.lark.refuse_edits = True
    before = len(made.lark.posted())
    await pressed(
        made.chat, lark_press(made.chat, approver, offered[refused][1], option="needs_more_detail")
    )
    if await _decisions(h, refused) != [(made.approver, "rejected", "needs_more_detail")]:
        raise CheckFailedError("a rejection on the card was not in the ledger with its reason")
    fallback = FALLBACK_TEMPLATE.format(suspension=refused, state="rejected")
    if len(made.lark.edits()) != 2 or [
        (kind, where, text) for kind, where, text, _ in made.lark.posted()[before:]
    ] != [("open_id", approver, fallback)]:
        raise CheckFailedError("a refused replacement was not followed by the text fallback")


def _decided_body(lark: _CardLark, suspension_id: str, state: str) -> str:
    """The body the decided card should carry: the offered card's, then the decision."""
    from brain.channels.cards import DECIDED_LINE

    for _, _, text, card in lark.posted():
        if card is not None and card["elements"][1]["actions"][0]["value"]["suspension_id"] == (
            suspension_id
        ):
            head = text.rsplit("\n", 1)[0]
            return f"{head}\n{DECIDED_LINE.format(state=state)}"
    raise CheckFailedError("the decided card had never been sent")


# ------------------------------------------------------------------ 3. group chat and policy
@check(
    leaves=("M10.7.4",),
    sentence=(
        "In Lark groups of bound reserved people each hears the room's floor and the asker their "
        "own answer privately or a link to Ask, as the room check shows; then a reply marked "
        "restricted is refused by the install's send step on Lark, whose ceiling is confidential, "
        "and recorded as one it cannot carry, while one marked confidential is sent."
    ),
)
async def group_chat_and_channel_policy_hold_on_one_install(h: Harness) -> None:
    from brain.channel_routes import (
        deliveries_of,
        ledger_of,
        reach_of,
        records_of,
        secrets_of,
        transport_of,
    )
    from brain.channels.outbound import Outgoing, deliver
    from brain.core.field_policy import Classification
    from brain.gate.context import Channel
    from brain.ops.idempotency import Intent
    from brain.tables.channel import DeliveryOutcome, RefusedBecause

    await a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone(h)
    chat = await lark_app(h)
    request = chat.request()
    record = await records_of(request).get(Channel.LARK)
    to = f"user:{open_id()}"
    outcomes = []
    for highest in (Classification.RESTRICTED, Classification.CONFIDENTIAL):
        before = len(chat.lark.sent)
        delivered = await deliver(
            Outgoing(
                channel=Channel.LARK,
                to=to,
                intent=Intent(principal_id=h.actor, intent_ref=f"ceiling.{h.run}.{highest.value}"),
                text="A reply marked for the ceiling check.",
                highest=highest,
            ),
            record=record,
            secrets=secrets_of(request),
            reach=reach_of(request),
            transport=transport_of(request),
            ledger=ledger_of(request),
            deliveries=deliveries_of(request),
            now=datetime.now(UTC),
        )
        outcomes.append((delivered.outcome, delivered.reason, len(chat.lark.sent) - before))
    if outcomes != [
        (DeliveryOutcome.REFUSED, RefusedBecause.CANNOT_CARRY, 0),
        (DeliveryOutcome.SENT, None, 1),
    ]:
        raise CheckFailedError("Lark carried a class its ceiling excludes, or refused one it takes")
    recent = await deliveries_of(request).recent(Channel.LARK)
    if not any(one.entry.reason is RefusedBecause.CANNOT_CARRY for one in recent):
        raise CheckFailedError(
            "a reply above Lark's ceiling was not recorded as one it cannot carry"
        )
