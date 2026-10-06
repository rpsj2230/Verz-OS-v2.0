"""Approval cards in a chat: offered to the person who may decide, decided by their press alone.

`brain.channels.cards` has held the approval card since M10.2.3 was first written: a card built at
the approver's own reach, a press refused from anybody else, a close budget that keeps a reserve
for closing what was opened. Nothing sent one and nothing read a press, and a bound person's chat
admits read alone, so an approval could be decided in the console and nowhere else. This module is
the wiring, between the events route (`brain.channel_routes`), which verifies, claims and answers
the vendor, and the Approvals route (`brain.approval_routes`), whose `take_decision` is the one
function that decides an approval. There is no second decision path here and no second statement
of who may approve.

**A card is offered where its reader alone reads it, when they write about deciding (M10.2.3,
M10.7.1).** A bound person whose message is a decision word is told where approvals are decided,
and on a channel that carries approvals and cards each approval the Approvals screen would offer
them is sent as a card to a conversation only they read with the bot, never to a group. Which
approvals is `brain.approval_routes.shown_card`, the question the Approvals screen asks, at the
reach a press would decide under, so a card is offered exactly when pressing it could decide it.
The card's request is `brain.console.approvals.card`'s for that reach, rendered at it by
`brain.gate.approval_request.render_request`, which is what the same person reads on the Approvals
screen, and `build_approval_card` refuses one rendered for anybody else and makes the payload
itself: the asker's artefact never reaches the approver (needs-rupash 14, M33.8.1). Each card
goes once per approver and approval, keyed through the operation ledger, and every open draws on
the open half of the card ceiling. See `A_CARD_IS_OFFERED_WHERE_ITS_READER_ALONE_READS_IT`.

**A card is sent to each approver the moment an approval is raised, to the Lark address their
binding keeps (M10.2.7, needs-rupash 118).** Until 2026-09-29 a chat binding kept the digest of
the chat identity and never the identity, so nothing could address a bound person until they wrote
to the bot. The owner decided that the card should arrive when the approval is raised, so since
`0166` a Lark binding keeps its person's open id (`brain.ops.binding_store.StoredAddresses`), and
`send_raised` asks every addressed Lark binding's person the Approvals screen's own question about
the new approval, at the same listing reach the offer uses, and sends the card to the ones it would
offer it to, in their own chat with the bot. Nothing is sent to a binding with no address: one made
before `0166` gains its address the next time its person writes. Whether a press on the card
decides it is still `INSTALL_LARK_CARD_APPROVALS`. The card is keyed as the offer's is, per
approver and approval, so a raise retried sends it once. See
`A_CARD_IS_SENT_WHEN_AN_APPROVAL_IS_RAISED_TO_WHOEVER_MAY_DECIDE_IT`.

**A press decides only as the person the card was built for, only while it is open at its
digest, and only as the permission allows (M10.2.3, needs-rupash 16).** The press value names the
suspension, its action digest and whom the card was built for; the presser's chat account must be
bound to that principal, so a press by anybody else in a group, or on a card forwarded to them,
decides nothing. The stored suspension must be the one the card named, at the same digest, and
open: `take_decision` holds its row and asks `card` at the press reach, so a press after it was
decided in the console, by another approver, or after it lapsed is refused by the store and not
by anything this module remembers. The press reach is `brain.gate.admission.admit_card_press`, a
binding's read and the `approve` verb under the channel's ceiling, from the presser's own grants,
and a message never gets it. A replayed press is refused before any of this, by the claim on the
callback's own id. Every refusal is one sentence, whatever the reason, so a press cannot learn
which reason it was. See `A_PRESS_DECIDES_ONLY_AS_THE_PERSON_THE_CARD_WAS_BUILT_FOR`.

**A decided card is closed by a patch within the card ceiling, and a refused one in the answer
(M10.2.4).** Two cases and two paths, each chosen for its case. A press that decided knows the
state the card is now in, which is the only thing `close_card` and `FALLBACK_TEMPLATE` can say, so
its card is closed after the vendor has been answered: the close half of the ceiling is asked, the
card is replaced by `PATCH` of its message, and when the patch is refused the text fallback goes to
the approver's own chat, drawn from the same half again. It is made after the answer because the
decision's own transaction can widen a document and every passage of it, and a card carried in an
answer Lark stopped waiting for is a card never replaced. A press that decided nothing knows no
state it may say (a decided row is not readable at the presser's reach, and saying who decided it
would be telling), so its card is replaced in the callback's own answer by a card with nothing to
press, which costs no call against any ceiling. Rejected: carrying the decided card in the answer
too, which spends nothing but depends on Lark still listening. See
`A_DECIDED_CARD_IS_PATCHED_AND_A_REFUSED_ONE_CLOSED_IN_THE_ANSWER`.

**A card carries no Take over control, because no card carries an agent's action.** Taking over
is offered on an agent's prepared action (M33.6.1.3), which is offered to an approver holding the
action's own capability, and a press admits read and approve alone. A test holds both halves, so
the day a press admits more, the missing control is a red test. See
`A_CARD_CARRIES_NO_AGENT_ACTION_SO_NOTHING_ON_IT_IS_TAKEN_OVER`.

**A card decides only while the install says it may, and every install ships saying it may not
(needs-rupash 117).** A press relies on Lark's own sign-in, and the product cannot see whether that
sign-in had a second factor, which a decision in the console asks for. So `INSTALL_LARK_CARD_
APPROVALS` is a switch an administrator turns on Install, Settings, read here through
`brain.install.value_of` and nowhere else, and off by default. Off, an approver who writes about
deciding is still sent each card, with its body and no control on it, and a line saying to decide
it in the console with the Approvals page; a press, from a card sent while the switch was on, is
told the same and never reaches `take_decision`, and `admit_card_press` admits it read alone behind
that. On, everything below is what happens. See `A_CARD_DECIDES_ONLY_WHILE_THE_INSTALL_SAYS_IT_MAY`.

**The card windows are the install's, and a check's are its own.** On a running install a window
lives in Valkey through `brain.ops.limit_store`, asked and recorded once through
`brain.channels.cards.close_admitted`; a process without Valkey admits, which is
`brain.ops.limit_store.UNREACHABLE_POLICY` for a channel's window. A test or an install check puts
`HeldCardWindows` on the application, because a check may not touch a key another caller uses.

Task ids: M10.2.3, M10.2.4, M10.7.1, M10.2.7
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Protocol

import structlog
from fastapi import Request

from brain.api_routes import limit_store_of, wiring_of
from brain.approval_routes import (
    A_REQUEST_THAT_NO_LONGER_APPLIES,
    DecidableVerdict,
    DecisionAsked,
    RejectionReason,
    SuspensionStore,
    shown_card,
    suspensions_of,
    take_decision,
)
from brain.attribution import trace_of_request
from brain.channels.adapter import CardAction, CardWire, Feature, adapter_for, channel_wires
from brain.channels.cards import (
    FALLBACK_TEMPLATE,
    ApprovalCard,
    CardCall,
    CardRefusedError,
    CardStaleError,
    PatchOutcome,
    build_approval_card,
    buttons,
    card_limit,
    close_admitted,
    press_value,
    read_press_value,
    render_card,
    render_decided,
    render_for_the_console,
)
from brain.channels.inbound import (
    DECIDE_WHERE_TOLD,
    ChannelBindings,
    Inbound,
    Pressed,
    prompt_intent,
    reply_intent,
)
from brain.channels.outbound import Delivered, Outgoing
from brain.chat_answer import People, ask_link, people_of
from brain.console.approvals import Card
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.gate.admission import admit_card_press, verbs_for_channel
from brain.gate.context import Channel
from brain.gate.ingress import Binding, Unrecognised, identity_hash
from brain.gate.leash import ApprovalState, SuspendedAction
from brain.gate.resolve import resolve
from brain.install import value_of
from brain.ops.channel_store import ChannelRecord
from brain.ops.idempotency import Intent
from brain.ops.lark_connect import ASK_PATH
from brain.ops.limit_store import ValkeyWindowStore
from brain.ops.limits import LimitDecision, LimiterState, check
from brain.tables.channel import DeliveryOutcome

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons

#: Why a card goes only where its reader alone reads it, and only for what they could decide.
A_CARD_IS_OFFERED_WHERE_ITS_READER_ALONE_READS_IT: Final = (
    "An approval card is offered to a bound person who wrote about deciding, in a conversation "
    "only they read with the bot and never in a group, for each approval the Approvals screen "
    "would offer them at the reach a press would decide under, with the body that screen shows "
    "them. A control in a room is a control the room can press, and a card for an approval its "
    "reader could not decide is a button that can only fail."
)

#: Why a card goes out when an approval is raised, and to whom.
A_CARD_IS_SENT_WHEN_AN_APPROVAL_IS_RAISED_TO_WHOEVER_MAY_DECIDE_IT: Final = (
    "When an approval is raised, every person bound in Lark with an address kept is asked the "
    "Approvals screen's own question about it at the reach a card is listed under, and each one "
    "it would be offered to is sent its card in their own chat with the bot; nobody else is sent "
    "anything, and a binding with no address is sent nothing until its person next writes "
    "(needs-rupash 118)."
)

#: Why a press decides only as the person the card was built for.
A_PRESS_DECIDES_ONLY_AS_THE_PERSON_THE_CARD_WAS_BUILT_FOR: Final = (
    "A press is honoured only from the chat account bound to the principal the card was built "
    "for, on the suspension it names at the digest it names, while the stored row is open and "
    "that person's own permission admits it, through the Approvals route's take_decision. A "
    "press by anybody else, after a decision elsewhere or after the window, or replayed, "
    "decides nothing, and every refusal is one sentence."
)

#: Why a card carries no Take over control.
A_CARD_CARRIES_NO_AGENT_ACTION_SO_NOTHING_ON_IT_IS_TAKEN_OVER: Final = (
    "Taking over is offered on an agent's prepared action and never on a person's own request, and "
    "an agent's action is offered to an approver who holds the action's own capability. A press is "
    "admitted read and approve and nothing else, so no card can carry an agent's action and every "
    "card is a promotion, which is approved or rejected. Take over is decided in the console and "
    "the staff web application until a press is admitted an action's own verb, which is when a "
    "third control belongs here, mapped by decision_asked to the Approvals route's own verdict."
)

#: Why a card decides nothing unless the install's switch says it may.
A_CARD_DECIDES_ONLY_WHILE_THE_INSTALL_SAYS_IT_MAY: Final = (
    "A press relies on Lark's own sign-in, and the product cannot see whether it had a second "
    "factor, which a decision in the console asks for. So a card may approve only while the "
    "install's Approve from Lark cards switch is on, and it ships off: off, the card is sent with "
    "no control and a line to decide it in the console, and a press never reaches take_decision."
)

#: Why a decided card is patched and a refused one closed in the callback's answer.
A_DECIDED_CARD_IS_PATCHED_AND_A_REFUSED_ONE_CLOSED_IN_THE_ANSWER: Final = (
    "A press that decided knows the state its card is now in, so the card is replaced after the "
    "vendor is answered, within the close half of the card ceiling, with the text fallback when "
    "the replacement is refused. A press that decided nothing knows no state it may say, so its "
    "card is replaced in the callback's own answer by one with nothing to press, at no cost."
)

# --------------------------------------------------------------------------- words

#: What a press that decided nothing is told, whatever the reason: one sentence for every reason,
#: so a press cannot learn whether it was the wrong person, a decided card or a lapsed one.
PRESS_REFUSED_TOLD: Final = (
    "This approval is not open to you here, so nothing was decided. The Approvals screen in the "
    "console shows what is waiting on you."
)

#: What a press is told when nothing on this process can decide it.
PRESS_NOT_TAKEN_TOLD: Final = (
    "Nothing was decided: approvals cannot be decided from here just now. Use the Approvals "
    "screen in the console."
)

#: What the card says once a press decided nothing on it.
CLOSED_TOLD: Final = (
    "This approval is no longer open here. The Approvals screen in the console shows what is "
    "waiting on you."
)

#: What a press that decided is told, by what it decided.
DECIDED_TOLD: Final[Mapping[ApprovalState, str]] = {
    ApprovalState.APPROVED: "Approved. It is recorded under your name.",
    ApprovalState.REJECTED: "Rejected. It is recorded under your name, with your reason.",
}

#: What the reject control says before a reason is chosen.
REJECT_PROMPT: Final = "Reject because..."

#: The reasons a rejection gives, in the words the console's Approvals screen uses for them
#: (`console/src/pages/approvalsQuery.ts`, `REJECTION_REASONS`); a test holds the two equal.
REJECTION_WORDS: Final[Mapping[RejectionReason, str]] = {
    RejectionReason.NOT_WHAT_WAS_ASKED: "It is not what was asked for",
    RejectionReason.WRONG_TARGET: "It is aimed at the wrong record",
    RejectionReason.NO_LONGER_NEEDED: "It is no longer needed",
    RejectionReason.NEEDS_MORE_DETAIL: "It needs more detail first",
}

#: The console's Approvals page, under the install's own address.
APPROVALS_PATH: Final = "/approvals"

#: The installation setting that lets a card decide. See the named constant above.
APPROVE_FROM_CARDS: Final = "INSTALL_LARK_CARD_APPROVALS"

#: Where a card says to decide it, on an install that names no address of its own.
THE_APPROVALS_SCREEN: Final = "the Approvals screen"

#: What a press is told while the switch is off, whoever pressed and whatever the card said.
DECIDE_IN_THE_CONSOLE_TOLD: Final = (
    "Approving from Lark is switched off on this install, so nothing was decided. Decide this on "
    "the Approvals screen in the console."
)

#: The most cards one message is answered with, soonest to lapse first. A bound on what one
#: message costs the open half of the card ceiling, and never a statement about the rest: the
#: sentence already says the Approvals screen lists everything waiting.
MAX_CARDS_OFFERED: Final = 5


# ------------------------------------------------------------------------ the windows


class CardWindows(Protocol):
    """Where the card ceiling's two windows are asked and recorded. One hit per call admitted."""

    async def spend(self, call: CardCall, now: datetime) -> LimitDecision:
        """Whether one more request of this kind may go now; recorded when it may."""
        ...


@dataclass
class SharedCardWindows:
    """The install's windows, in Valkey through `brain.ops.limit_store`, or none without it."""

    store: ValkeyWindowStore | None

    async def spend(self, call: CardCall, now: datetime) -> LimitDecision:
        if self.store is None:
            # No windows to count in, and a channel's window admits then: see the module note.
            return check(now=now, limits=(), state=LimiterState())
        verdict = await asyncio.to_thread(
            self.store.check_and_record, now=now, limits=(card_limit(call),)
        )
        return verdict.decision


@dataclass
class HeldCardWindows:
    """The two windows in memory, for a test and for an install check, which may not touch a key
    another caller uses."""

    state: LimiterState = field(default_factory=LimiterState)

    async def spend(self, call: CardCall, now: datetime) -> LimitDecision:
        limit = card_limit(call)
        decision = check(now=now, limits=(limit,), state=self.state)
        if decision.allowed:
            self.state = self.state.record(now, (limit,))
        return decision


def cards_may_approve(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> bool:
    """Whether this install lets a card decide: its switch reads `on`, and nothing else does.

    Read through `value_of`, the one reader of an installation value, and compared with the one
    word that switches it on, so a value nobody meant (a typo, a blank saved row) leaves it off.
    """
    return value_of(APPROVE_FROM_CARDS, env, saved) == "on"


def card_windows_of(request: Request) -> CardWindows:
    """`app.state.card_windows` when a test or a check put one there, the install's otherwise."""
    found = getattr(request.app.state, "card_windows", None)
    if isinstance(found, SharedCardWindows | HeldCardWindows):
        return found
    return SharedCardWindows(limit_store_of(request.app.state))


# ------------------------------------------------------------------------ the pieces


def carries_cards(channel: Channel) -> bool:
    """Whether an approval card may be offered on this channel at all.

    Three facts and all three: its ceiling carries `approve`, its adapter declares cards, and its
    wire can post one. The first is `brain.gate.admission`'s, so a channel whose ceiling changes
    changes this at the same moment.
    """
    wire = channel_wires().get(channel)
    return (
        "approve" in verbs_for_channel(channel)
        and adapter_for(channel).capabilities().supports(Feature.CARDS)
        and isinstance(wire, CardWire)
    )


def controls_for(approve: Mapping[str, str], reject: Mapping[str, str]) -> tuple[CardAction, ...]:
    """Approve as a button, and Reject as a choice of the reasons the console offers.

    A rejection names its reason (`brain.approval_routes.DecisionAsked`), so the reject control is
    the four reasons and a press on it carries the one chosen; a card that rejected with no reason
    would be refused by the route or record a reason nobody gave.
    """
    return (
        CardAction(text="Approve", value=approve),
        CardAction(
            text=REJECT_PROMPT,
            value=reject,
            options=tuple((reason.value, REJECTION_WORDS[reason]) for reason in RejectionReason),
        ),
    )


def card_controls(card: ApprovalCard) -> tuple[CardAction, ...]:
    """The controls on this card, each carrying `press_value` for its own decision."""
    approve = next(one for one in buttons() if one.decision is ApprovalState.APPROVED)
    reject = next(one for one in buttons() if one.decision is ApprovalState.REJECTED)
    return controls_for(press_value(card, approve), press_value(card, reject))


def built(
    suspension: SuspendedAction, shown: Card, *, reach: EntitlementSet, channel: Channel
) -> ApprovalCard:
    """The card for this approval at this reach: the body the Approvals screen shows them.

    One card id per approval, reader and action, so the card offered and the card closed are the
    same card and a send is keyed once for each reader. `shown` is what the Approvals screen shows
    this reader, so the card cannot show them anything that screen would not. `CardRefusedError`
    from `build_approval_card` for a request rendered for anybody but the reader at their reach.
    """
    key = _key(suspension.id, reach.principal_id, suspension.action_digest)
    return build_approval_card(
        card_id=f"card.{key}",
        suspension_id=suspension.id,
        action_digest=suspension.action_digest,
        request=shown.request,
        runs_as=shown.runs_as,
        approver=reach,
        raised_at=suspension.raised_at,
        expires_at=suspension.expires_at,
        capabilities=adapter_for(channel).capabilities(),
    )


def decision_asked(decision: ApprovalState, option: str) -> DecisionAsked | None:
    """The route's body for what a press chose, or None for a press that chose nothing it can.

    An approval chooses no option; a rejection chooses one of `RejectionReason`. Anything else is
    not a press on a card this module built.
    """
    if decision is ApprovalState.APPROVED and not option:
        return DecisionAsked(verdict=DecidableVerdict.APPROVED)
    if decision is ApprovalState.REJECTED and option in {one.value for one in RejectionReason}:
        return DecisionAsked(verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason(option))
    return None


def approvals_link() -> str:
    """The install's Approvals page, or empty on an install that names no address of its own.

    From the same address the chat's link to Ask is made from, so the two cannot disagree about
    where this install is.
    """
    ask = ask_link()
    return f"{ask.removesuffix(ASK_PATH)}{APPROVALS_PATH}" if ask.endswith(ASK_PATH) else ""


def where_to_decide(link: str) -> str:
    """`DECIDE_WHERE_TOLD`, and the Approvals page when the install has an address of its own."""
    return f"{DECIDE_WHERE_TOLD} Open Approvals: {link}" if link else DECIDE_WHERE_TOLD


def _key(*parts: str) -> str:
    blob = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------------ the cards


type ReachLoader = Callable[[str, datetime], Awaitable[EntitlementSet]]


def nominal_reach(request: Request) -> ReachLoader:
    """A person's own grants, resolved as `brain.api_routes.asking` resolves a caller's."""

    async def load(principal_id: str, now: datetime) -> EntitlementSet:
        wiring = wiring_of(request)
        if wiring is None:
            raise Failed("no gate wiring on this process")
        resolved = await resolve(
            principal_id,
            versions=wiring.versions,
            store=wiring.store,
            cache=wiring.cache,
            now=now,
        )
        return resolved.entitlements

    return load


@dataclass
class ApprovalCards:
    """`brain.channels.inbound.ApprovalOfferer` and `CardPresser`: offers cards, decides presses.

    Built per request by `of`, from that request's bindings, directory, suspension store, gate
    and card windows, so a test's in-memory ones are the ones used.
    """

    bindings: ChannelBindings
    people: People
    store: SuspensionStore | None
    reach_of: ReachLoader
    windows: CardWindows
    trace_id: str
    #: The install's Approve from Lark cards switch, as `cards_may_approve` read it.
    switched_on: bool
    link: str = ""

    @classmethod
    def of(cls, request: Request, *, bindings: ChannelBindings) -> ApprovalCards:
        """The cards for this request. The switch is `app.state.approve_from_cards` when a test or
        an install check put a boolean there, which is how a check runs both states on its own
        application, and the install's own setting otherwise."""
        found = suspensions_of(request)
        stated = getattr(request.app.state, "approve_from_cards", None)
        return cls(
            bindings=bindings,
            people=people_of(request),
            store=found if isinstance(found, SuspensionStore) else None,
            reach_of=nominal_reach(request),
            windows=card_windows_of(request),
            trace_id=trace_of_request() or f"card-{uuid.uuid4().hex[:16]}",
            switched_on=stated if isinstance(stated, bool) else cards_may_approve(),
            link=approvals_link(),
        )

    # ------------------------------------------------------------------ the offer

    def told(self) -> str:
        """What a decision word is answered with on this install. See `where_to_decide`."""
        return where_to_decide(self.link)

    async def offer(
        self,
        inbound: Inbound,
        *,
        binding: Binding,
        record: ChannelRecord,
        reply_to: str,
        now: datetime,
    ) -> tuple[Outgoing, ...]:
        """Where approvals are decided, and each one waiting on this person as a card.

        The sentence goes first and to everybody alike. A binding to somebody disabled or gone is
        told what an unbound sender is told, as `brain.chat_answer.ChatAnswerer` tells them. See
        `A_CARD_IS_OFFERED_WHERE_ITS_READER_ALONE_READS_IT`.
        """
        event = inbound.event
        conversation = inbound.conversation
        shared = conversation is not None and conversation.shared
        mine = conversation.sender_to if shared and conversation is not None else reply_to
        person = await self.people.live(binding.principal_id)
        if person is None or not person.is_active(now):
            return (
                Outgoing(
                    channel=event.channel,
                    to=mine,
                    intent=prompt_intent(record, binding.identity_hash),
                    text=Unrecognised(channel=event.channel).prompt,
                ),
            )
        told = Outgoing(
            channel=event.channel, to=mine, intent=reply_intent(record, event), text=self.told()
        )
        if self.store is None or not carries_cards(event.channel):
            return (told,)
        nominal = await self.reach_of(person.id, now)
        # Who may decide each approval and what the Approvals screen shows them: the permission,
        # under the channel's ceiling. A listing, never a decision; a press is admitted under the
        # install's switch, in `press`.
        reach = admit_card_press(nominal, event.channel, switched_on=True)
        waiting = await self.store.reading_as(reach, now).open_suspensions()
        offered = sorted(
            ((one, shown) for one in waiting if (shown := shown_card(one, reach, now)) is not None),
            key=lambda pair: (pair[1].expires_at, pair[1].suspension_id),
        )[:MAX_CARDS_OFFERED]
        cards: list[Outgoing] = []
        for suspension, shown in offered:
            if not (await self.windows.spend(CardCall.OPEN, now)).allowed:
                # The open half is spent; the sentence already names the Approvals screen.
                log.info("approval card not offered: open window full")
                break
            try:
                card = built(suspension, shown, reach=reach, channel=event.channel)
            except CardRefusedError:
                log.warning("approval card not built", suspension=suspension.id)
                continue
            cards.append(
                self._offered(
                    card, channel=event.channel, to=mine, person=person.id, nominal=nominal
                )
            )
        return (told, *cards)

    def _offered(
        self,
        card: ApprovalCard,
        *,
        channel: Channel,
        to: str,
        person: str,
        nominal: EntitlementSet,
    ) -> Outgoing:
        """One card as it is sent: with its controls while the switch is on, with none and the
        console named in their place while it is off. Keyed apart, so switching it on sends the
        card with controls to somebody already sent the one without."""
        if self.switched_on:
            kind, text, controls = "approval_card", render_card(card), card_controls(card)
        else:
            where = self.link or THE_APPROVALS_SCREEN
            kind, text, controls = "approval_notice", render_for_the_console(card, where), ()
        return Outgoing(
            channel=channel,
            to=to,
            intent=Intent(principal_id=person, intent_ref=f"{kind}.{card.card_id}"),
            text=text,
            payload=card.payload,
            recipient=person,
            planned_hash=nominal.ent_hash(),
            card=True,
            actions=controls,
        )

    # ------------------------------------------------------------------ the raise

    async def raised(
        self,
        suspension: SuspendedAction,
        *,
        channel: Channel,
        addressed: tuple[tuple[str, str], ...],
        now: datetime,
    ) -> tuple[Outgoing, ...]:
        """The card each addressed person who may decide this approval is sent as it is raised.

        One question per person, the Approvals screen's (`shown_card`), at the listing reach the
        offer uses, so a card goes to exactly the people that screen would offer it to and to no
        one it would not. Each card draws on the open half of the card ceiling; a full window
        sends no more, and the approval still waits on the screen. See
        `A_CARD_IS_SENT_WHEN_AN_APPROVAL_IS_RAISED_TO_WHOEVER_MAY_DECIDE_IT`.
        """
        wire: object = channel_wires().get(channel)
        if not carries_cards(channel) or not isinstance(wire, CardWire):
            return ()
        cards: list[Outgoing] = []
        for principal_id, address in addressed:
            person = await self.people.live(principal_id)
            if person is None or not person.is_active(now):
                continue
            nominal = await self.reach_of(person.id, now)
            reach = admit_card_press(nominal, channel, switched_on=True)
            shown = shown_card(suspension, reach, now)
            if shown is None:
                continue
            if not (await self.windows.spend(CardCall.OPEN, now)).allowed:
                log.info("approval card not sent on raise: open window full")
                break
            try:
                card = built(suspension, shown, reach=reach, channel=channel)
            except CardRefusedError:
                log.warning("approval card not built", suspension=suspension.id)
                continue
            cards.append(
                self._offered(
                    card,
                    channel=channel,
                    to=wire.person_address(address),
                    person=person.id,
                    nominal=nominal,
                )
            )
        return tuple(cards)

    # ------------------------------------------------------------------ the press

    async def press(
        self, inbound: Inbound, *, record: ChannelRecord, reply_to: str, now: datetime
    ) -> Pressed:
        """Decide this press through `take_decision`, or say in one sentence it decided nothing.

        See `A_PRESS_DECIDES_ONLY_AS_THE_PERSON_THE_CARD_WAS_BUILT_FOR` for the order and
        `A_DECIDED_CARD_IS_PATCHED_AND_A_REFUSED_ONE_CLOSED_IN_THE_ANSWER` for what closes it.
        """
        pressed = inbound.press
        if pressed is None:
            msg = "only a press on a card is decided here"
            raise ValueError(msg)
        if not self.switched_on:
            # Before anything is looked up: a press decides nothing while the switch is off,
            # whoever pressed and whatever the card named. See the named constant.
            return Pressed(told=DECIDE_IN_THE_CONSOLE_TOLD)
        event = inbound.event
        named = read_press_value(pressed.value)
        if named is None:
            return Pressed(told=PRESS_REFUSED_TOLD)
        digest = identity_hash(event.channel, event.channel_identity)
        binding = await self._binding(event.channel, digest)
        if binding is None or binding.principal_id != named.rendered_for:
            # Somebody else's press, in a group or on a forwarded card: their copy is theirs to
            # look at and nothing here touches it.
            return Pressed(told=PRESS_REFUSED_TOLD)
        person = await self.people.live(binding.principal_id)
        asked = decision_asked(named.decision, pressed.option)
        if person is None or not person.is_active(now) or asked is None:
            return Pressed(told=PRESS_REFUSED_TOLD)
        if self.store is None:
            return Pressed(told=PRESS_NOT_TAKEN_TOLD)
        nominal = await self.reach_of(person.id, now)
        reach = admit_card_press(nominal, event.channel, switched_on=self.switched_on)
        found = await self.store.reading_as(reach, now).suspension(named.suspension_id)
        if found is None or found.action_digest != named.action_digest:
            return Pressed(told=PRESS_REFUSED_TOLD, closed=CLOSED_TOLD)
        shown = shown_card(found, reach, now)
        if shown is None:
            return Pressed(told=PRESS_REFUSED_TOLD, closed=CLOSED_TOLD)
        try:
            decided = await take_decision(
                self.store, found.id, reach, asked, trace_id=self.trace_id, now=now
            )
        except Absent as refused:
            moved = refused.public_message == A_REQUEST_THAT_NO_LONGER_APPLIES
            told = A_REQUEST_THAT_NO_LONGER_APPLIES if moved else PRESS_REFUSED_TOLD
            return Pressed(told=told, closed=CLOSED_TOLD)
        except Failed:
            return Pressed(told=PRESS_NOT_TAKEN_TOLD)
        log.info("approval decided on a card", verdict=asked.verdict.value)
        return await self._closing(
            found,
            shown,
            decided.suspension.state,
            message_id=pressed.message_id,
            reply_to=reply_to,
            reach=reach,
            nominal=nominal,
            channel=event.channel,
            now=now,
        )

    async def _binding(self, channel: Channel, digest: str) -> Binding | None:
        return await self.bindings.binding_for(channel, digest)

    async def _closing(
        self,
        suspension: SuspendedAction,
        shown: Card,
        state: ApprovalState,
        *,
        message_id: str,
        reply_to: str,
        reach: EntitlementSet,
        nominal: EntitlementSet,
        channel: Channel,
        now: datetime,
    ) -> Pressed:
        """The decided card's replacement and its fallback, drawn from the close half."""
        told = DECIDED_TOLD[state]
        # Typed as an object: whether a wire can edit a card is a question about its class.
        wire: object = channel_wires().get(channel)
        capabilities = adapter_for(channel).capabilities()
        try:
            card = built(suspension, shown, reach=reach, channel=channel)
            key = card.card_id
            plan = close_admitted(
                card,
                state=state,
                decision=await self.windows.spend(CardCall.CLOSE, now),
                capabilities=capabilities,
            )
        except CardStaleError:
            log.info("approval card not closed: close window full")
            return Pressed(told=told, decided=True)
        except CardRefusedError:
            log.warning("approval card not closed", suspension=suspension.id)
            return Pressed(told=told, decided=True)
        fallback = Outgoing(
            channel=channel,
            to=reply_to,
            intent=Intent(principal_id=reach.principal_id, intent_ref=f"approval_stale.{key}"),
            text=FALLBACK_TEMPLATE.format(suspension=suspension.id, state=state.value),
        )
        if plan.outcome is PatchOutcome.TEXT_FALLBACK or not isinstance(wire, CardWire):
            return Pressed(told=told, decided=True, fallback=fallback)
        patch = Outgoing(
            channel=channel,
            to=wire.edit_address(message_id),
            intent=Intent(principal_id=reach.principal_id, intent_ref=f"approval_closed.{key}"),
            text=render_decided(plan.card),
            payload=card.payload,
            recipient=reach.principal_id,
            planned_hash=nominal.ent_hash(),
        )
        return Pressed(told=told, decided=True, patch=patch, fallback=fallback)


async def send_raised(request: Request, suspension: SuspendedAction) -> int:
    """Send the cards for an approval just raised, through the events route's own send step.

    What a route calls once the approval is committed: the Lark channel's record, the addressed
    bindings, `ApprovalCards.raised`, and `brain.channel_routes`' `deliver` with that request's
    secrets, transport, ledger and deliveries, so each card is sent once and recorded as any reply
    is. How many were delivered, for a test. Nothing is sent on an install whose Lark channel is
    not switched on. Whatever fails is logged by its kind and never reaches the person who raised
    the approval, whose request has already been answered.
    """
    # Imported here: `brain.channel_routes` imports this module to decide presses.
    from brain.channel_routes import _deliver, addresses_of, bindings_of, records_of

    try:
        record = await records_of(request).get(Channel.LARK)
        if record is None or not record.enabled:
            return 0
        book = addresses_of(request)
        if book is None:
            return 0
        now = datetime.now(UTC)
        cards = ApprovalCards.of(request, bindings=bindings_of(request))
        planned = await cards.raised(
            suspension,
            channel=Channel.LARK,
            addressed=await book.addressed(Channel.LARK),
            now=now,
        )
        sent = 0
        for one in planned:
            delivered = await _deliver(request, one, record, datetime.now(UTC))
            sent += delivered.outcome is DeliveryOutcome.SENT
        return sent
    except Exception as exc:
        log.warning("approval cards not sent on raise", kind=type(exc).__name__)
        return 0


async def closed_after(
    pressed: Pressed,
    *,
    send: Callable[[Outgoing], Awaitable[Delivered]],
    windows: CardWindows,
    now: datetime,
) -> None:
    """Replace a decided card, and send the text fallback when the replacement did not go.

    The fallback after a refused patch is a second request, so it draws on the close half again;
    a fallback planned instead of a patch was drawn when the plan was made.
    """
    if pressed.patch is not None:
        delivered = await send(pressed.patch)
        if delivered.outcome is DeliveryOutcome.SENT or pressed.fallback is None:
            return
        if not (await windows.spend(CardCall.CLOSE, now)).allowed:
            log.info("approval card fallback not sent: close window full")
            return
    if pressed.fallback is not None:
        await send(pressed.fallback)
