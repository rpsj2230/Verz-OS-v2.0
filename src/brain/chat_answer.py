"""A bound person's chat message, answered by the code the web's Ask runs, at the reach they hold.

The owner's test for the Lark channel is one sentence: a bound person asks in a direct message and
gets the same answer Ask gives them on the web, and in a group each person gets an answer at their
own reach, privately or as a link, and never another person's. This module keeps that sentence,
between the events route (`brain.channel_routes`), which verifies, claims and delivers, and the
answer lane, which it does not copy.

**The same answer is the same function (M2.3.1, M38.2.2.3).** `brain.api_routes.answered_for` is
the body of the web's `/answer` taken out of the route, and this calls it with an `Answering` for
the bound person: the principal from the directory, their grants resolved as `asking` resolves
them, admitted for the chat channel at `Assurance.BOUND`. For reading, which is all an answer does,
that reach is the web's: `brain.gate.admission` gives a binding the read verb and withholds only
effects, for which a message is not a signature. The frames the lane wrote are read back into chat
text, the prose and then its sources. See `A_CHAT_ANSWER_IS_THE_WEB_ANSWER`.

Rejected: rendering from `Answered.composed`. An abstention, a refusal and a cache hit carry none,
and their words are in the frames alone, so reading the frames is the only way every outcome says
in chat what it says on the web.

**A direct message is answered at the asker's reach, to them (M10.2.6).** One reader, and the
direct path of `brain.channels.lark.plan_delivery` holds that there is one.

**A group is answered at the floor of everybody in it, and the asker privately at their own
(M10.4.1, M10.4.2, M10.2.5).** Who is present is read live from the vendor when the question is
asked, each person is looked up by the digest of their id, and a person bound to nobody holds
nothing, which makes the floor nothing. So in the usual group the room is told nothing and the
asker reads their own answer in a card only they see; where everybody present holds what the asker
holds, the room reads it. A room posting is computed by the same function at the floor's reach,
and `plan_delivery` refuses one computed at any other. A floor answer that found nothing is not
posted beside a private aside: an abstention in front of the room tells it nothing. See
`A_GROUP_IS_ANSWERED_AT_ITS_FLOOR_AND_THE_ASKER_ALONE_AT_THEIRS`.

**Where nothing may be said, or the surface has no private way to say it, a link (M10.4.3).** The
link is the install's Ask page and carries nothing, so following it runs the gate again for
whoever clicks. An answer holding a field above the channel's ceiling (M10.1.3) is the link too.

**The room is read again before anything is sent (M10.4.4).** An answer can take seconds and a
person who joined meanwhile was not counted in the floor. So who is present is read a second time
once the answers are made, and a room that changed, or whose floor moved, has its posting dropped,
by `brain.channels.room.revalidate`; the asker's aside, which only they read, still goes.
`brain.channels.outbound.deliver` then holds each message to the asker's reach at the instant it
leaves (M10.4.5). A room that cannot be read at all is a room whose floor is unknown, and it is
answered as a floor of nothing.

**A person's messages in one chat are one thread, kept as the web keeps its own (M9.1.2).** The
asker's own answer is written through `brain.chat.remember` under a thread named for the chat, so
the web lists and continues it; a room's floor answer is never kept. See `THIS_CHAT_IS_ONE_THREAD`.

Task ids: M10.2.2, M10.2.5, M10.2.6, M10.4.1, M10.4.2, M10.4.3, M10.4.4, M2.3.1, M1.8.5, M38.2.2.3
Task ids: M9.1.2
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api_routes import (
    Answering,
    Halted,
    Question,
    answered_for,
    field_policies,
    wiring_of,
)
from brain.attribution import trace_of_request
from brain.channels.adapter import (
    BOT_ID,
    ChannelCapabilities,
    ChannelTransport,
    Conversation,
    VendorAnswer,
    VendorRequest,
    adapter_for,
    channel_wires,
)
from brain.channels.cards import LABEL_PREFIX
from brain.channels.inbound import ChannelBindings, Inbound, prompt_intent, reply_intent
from brain.channels.lark import ChatType, LarkMessage, Rendered, Visibility, plan_delivery
from brain.channels.marks import mark_line
from brain.channels.outbound import Outgoing
from brain.channels.room import Member, RoomRefusedError, RoomRender, floor, revalidate
from brain.channels.room import plan as room_plan
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.core.field_policy import Classification, FieldPolicy
from brain.core.principal import Principal
from brain.core.redaction import ChannelPayload
from brain.gate.admission import Assurance, admit
from brain.gate.answer import Answered
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.context import Channel, open_trace
from brain.gate.ingress import Binding, ChannelEvent, Unrecognised, identity_hash
from brain.gate.model_lane import PASSAGE_POLICY
from brain.gate.resolve import resolve
from brain.gate.streaming import Event, citation_text
from brain.identity.principal_store import StoredPrincipals
from brain.install import InstallError, value_of
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY
from brain.ops.channel_store import ChannelRecord, ChannelSecrets, ChannelSecretsUnavailableError
from brain.ops.classification_store import classified_lane_of
from brain.ops.idempotency import Intent
from brain.ops.lark_connect import ask_address
from brain.ops.limit_store import StoreVerdict
from brain.ops.limits import refusal_sentence
from brain.routing_routes import sessions_of
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons

#: Why a chat answer is read out of the frames the web route streams.
A_CHAT_ANSWER_IS_THE_WEB_ANSWER: Final = (
    "A bound person's chat question is answered by brain.api_routes.answered_for, the function the "
    "web's Ask runs, for the same principal at the reach their grants give them on this channel, "
    "and the chat text is read out of the frames that function wrote. So the words, the sources "
    "and the refusals are the web's, and there is no second answer path to drift."
)

#: Why a group's room posting is made at the floor and the asker's answer goes to them alone.
A_GROUP_IS_ANSWERED_AT_ITS_FLOOR_AND_THE_ASKER_ALONE_AT_THEIRS: Final = (
    "In a group the people present are read live, each is looked up by the digest of their id, "
    "and anybody bound to nobody holds nothing. What the room reads is answered at the "
    "intersection of everybody's reach; what only the asker reads is answered at theirs; and "
    "nothing any other person holds decides what anybody reads."
)

# --------------------------------------------------------------------- the figures

#: The most people a group's floor is computed over. Beyond it the floor is taken as nothing,
#: which is the narrow direction: the asker still reads their own answer privately.
MAX_ROOM_MEMBERS: Final = 200

#: Pages of a room read at most, which `MAX_ROOM_MEMBERS` bounds anyway.
MAX_MEMBER_PAGES: Final = 3

#: The principal id a person bound to nobody stands in the room as. Theirs alone, so the membership
#: a render was made for can be compared, and never a principal anything can resolve.
UNBOUND_MEMBER: Final = "unbound."

EMPTY_TOLD: Final = "Ask me a question in words, after mentioning me in a group."
TOO_LONG_TOLD: Final = "That question is longer than I can take. Ask it in fewer words."
LINK_TOLD: Final = "I cannot answer that here. Open Ask to see the answer at your own access: "
CEILING_TOLD: Final = (
    "This answer holds information this chat may not carry. Open Ask to read it in the console: "
)
SOURCES_HEADING: Final = "Sources:"


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class ChatReply:
    """One question's answer as a chat sends it: the words, what they came from, how sensitive."""

    text: str
    payload: ChannelPayload
    highest: Classification
    #: True when the lane answered, false for an abstention or a refusal.
    answered: bool
    #: The request trace the answer ran under, which the reply offers for marking (M16.6.4).
    #: Empty for a sentence that ran no request. The room's posting is sent with it emptied, in
    #: `ChatAnswerer._planned`, which is the one place a room's answer leaves; see
    #: `brain.channels.marks`.
    trace_id: str = ""


class People(Protocol):
    """Who is here and not disabled, by principal id. `StoredPeople` over the directory."""

    async def live(self, principal_id: str) -> Principal | None: ...


@dataclass(frozen=True)
class StoredPeople:
    """`auth.principal`, through `brain.identity.principal_store.StoredPrincipals`."""

    sessions: async_sessionmaker[AsyncSession]

    async def live(self, principal_id: str) -> Principal | None:
        return await StoredPrincipals(self.sessions).live_principal(principal_id)


@runtime_checkable
class RoomReader(Protocol):
    """A wire that can say who is in one of its conversations. `brain.channels.lark.LarkWire`."""

    def members_request(
        self, *, conversation_id: str, page: str, secret: str, tenant: Mapping[str, str]
    ) -> VendorRequest: ...

    def members_page(self, answer: VendorAnswer) -> tuple[frozenset[str], str]: ...


# ------------------------------------------------------------------------ reading an answer


def _events(frames: Sequence[str]) -> list[tuple[str, str]]:
    """Each frame's event name and data, by the event-stream format's own rules."""
    found: list[tuple[str, str]] = []
    for frame in frames:
        name, data = "", []
        for line in frame.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if key == "event":
                name = value
            elif key == "data":
                data.append(value)
        if name:
            found.append((name, "\n".join(data)))
    return found


def chat_text(answered: Answered) -> str:
    """What the web's Ask shows, as one message: the prose, then its sources, or the failure."""
    prose: list[str] = []
    cited: list[str] = []
    failed = ""
    for name, data in _events(answered.frames):
        if name == Event.TEXT.value:
            prose.append(data)
        elif name == Event.CITATION.value:
            # The web's fields, read back into a sentence a chat can show (M8.1.1 to M8.1.3).
            cited.append(citation_text(data))
        elif name == Event.ERROR.value:
            failed = data
    if failed:
        return failed
    text = "".join(prose).strip()
    if cited:
        text = "\n".join((text, "", SOURCES_HEADING, *(f"- {one}" for one in cited)))
    return text


def highest_in(payload: ChannelPayload, policies: Mapping[str, FieldPolicy]) -> Classification:
    """The most sensitive classification of any field in the payload, from the policies the
    redactor used. What the channel's ceiling is held to (M10.1.3)."""
    top = Classification.INTERNAL
    for record in payload.records:
        entity = str(record.get("@entity") or record.get("entity") or "")
        policy = PASSAGE_POLICY if entity == KNOWLEDGE_ENTITY else policies.get(entity)
        if policy is None:
            continue
        for name in record:
            rule = policy.rule_for(entity, name)
            if rule is not None and rule.classification.rank > top.rank:
                top = rule.classification
    return top


def message_of(inbound: Inbound, conversation: Conversation) -> LarkMessage:
    """The message as `plan_delivery` reads it: the event and whether one person reads it."""
    return LarkMessage(
        event=inbound.event,
        chat_id=conversation.conversation_id,
        chat_type=ChatType.GROUP if conversation.shared else ChatType.DIRECT,
    )


def people_of(request: Request) -> People:
    """`app.state.chat_people` when a test put one there, the directory otherwise."""
    found: People | None = getattr(request.app.state, "chat_people", None)
    if found is not None:
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredPeople(sessions)


def ask_link() -> str:
    """The install's Ask page, or empty on an install that names no address of its own."""
    try:
        return ask_address(value_of("INSTALL_OIDC_REDIRECT_URIS"))
    except InstallError:
        return ""


# ------------------------------------------------------------------------ the answerer


#: Why a chat's messages from one person are one thread, and a room's floor is never kept.
THIS_CHAT_IS_ONE_THREAD: Final = (
    "A chat message carries no thread id, so a person's messages in one vendor conversation are "
    "one thread, named by the channel, the person and the conversation, and listed with their "
    "web threads so the web continues it. Only the asker's own answer is kept; an answer "
    "computed at a room's floor is the room's, at a reach that is not theirs."
)


class ChatAnswerer:
    """`brain.channels.inbound.ChannelAnswerer`: the gate, run as the bound person.

    Built per request by `brain.channel_routes.answerer_of`, with that request's secrets,
    transport and bindings, so a test's in-memory ones are the ones used.
    """

    def __init__(
        self,
        request: Request,
        *,
        secrets: ChannelSecrets,
        transport: ChannelTransport,
        bindings: ChannelBindings,
    ) -> None:
        self._request = request
        self._secrets = secrets
        self._transport = transport
        self._bindings = bindings

    async def answer(
        self,
        inbound: Inbound,
        *,
        binding: Binding,
        record: ChannelRecord,
        reply_to: str,
        now: datetime,
    ) -> tuple[Outgoing, ...]:
        event = inbound.event
        conversation = inbound.conversation
        people = people_of(self._request)
        person = await people.live(binding.principal_id)
        if person is None or not person.is_active(now):
            # A binding to somebody disabled or gone is a binding to nobody, and is told what
            # an unbound sender is told, so the two cannot be told apart.
            return (
                Outgoing(
                    channel=event.channel,
                    to=reply_to if conversation is None else conversation.sender_to,
                    intent=prompt_intent(record, binding.identity_hash),
                    text=Unrecognised(channel=event.channel).prompt,
                ),
            )
        question = inbound.address.question.strip()
        if not question or len(question) > MAX_QUESTION_CHARS:
            told = EMPTY_TOLD if not question else TOO_LONG_TOLD
            return (self._sentence(record, event, reply_to, told),)
        nominal = await self._nominal(person.id, now)
        reach = admit(nominal, event.channel, Assurance.BOUND)
        capabilities = adapter_for(event.channel).capabilities()
        if conversation is None:
            reply = await self._ask(person, reach, inbound, now, keep=True)
            return (self._outgoing(reply, reply_to, record, event, person, nominal, capabilities),)
        return await self._planned(
            inbound, conversation, person, nominal, reach, record, reply_to, capabilities, now
        )

    # ------------------------------------------------------------------ one question

    async def _nominal(self, principal_id: str, now: datetime) -> EntitlementSet:
        """The person's own grants, resolved as `brain.api_routes.asking` resolves a caller's."""
        wiring = wiring_of(self._request)
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

    async def _ask(
        self,
        person: Principal,
        reach: EntitlementSet,
        inbound: Inbound,
        now: datetime,
        *,
        keep: bool = False,
    ) -> ChatReply:
        """The web's answer to this question for this person at this reach. See the constant.

        `keep` writes the exchange to the person's thread for this chat (M9.1.1, M9.1.2), which is
        the asker's own answer and never a room's floor, computed at a reach that is not theirs.
        """
        channel = inbound.event.channel
        try:
            asked = Question(question=inbound.address.question, agent=inbound.address.agent_id)
        except ValidationError:
            return ChatReply(TOO_LONG_TOLD, ChannelPayload(), Classification.INTERNAL, False)
        trace = trace_of_request() or f"chat-{uuid.uuid4().hex[:16]}"
        outcome = await answered_for(
            self._request,
            open_trace(trace, now, channel),
            Answering(principal=person, reach=reach, channel=channel, now=now),
            asked,
        )
        if isinstance(outcome, StoreVerdict):
            decision = outcome.decision
            told = refusal_sentence(decision.binding, decision.retry_after_seconds)
            return ChatReply(told, ChannelPayload(), Classification.INTERNAL, False)
        if isinstance(outcome, Halted):
            return ChatReply(outcome.told, ChannelPayload(), Classification.INTERNAL, False)
        payload = outcome.composed.payload if outcome.composed is not None else ChannelPayload()
        text = chat_text(outcome)
        if payload.label and payload.label not in text:
            text = f"{LABEL_PREFIX}{payload.label}\n{text}"
        # The policies the redactor used: the registry's and the uploaded tables', as the
        # answer route merges them, so a classified column is held to the channel's ceiling too.
        registry = getattr(self._request.app.state, "tools", None)
        tables = await classified_lane_of(self._request.app.state)
        policies = {
            **(field_policies(registry) if isinstance(registry, ToolRegistry) else {}),
            **tables.policies,
        }
        if keep:
            await self._kept(person, inbound, asked, outcome, policies, now)
        return ChatReply(
            text,
            payload,
            highest_in(payload, policies),
            outcome.composed is not None,
            trace_id=trace,
        )

    async def _kept(
        self,
        person: Principal,
        inbound: Inbound,
        asked: Question,
        outcome: Answered,
        policies: Mapping[str, FieldPolicy],
        now: datetime,
    ) -> None:
        """This exchange, in the person's thread for this chat. See `THIS_CHAT_IS_ONE_THREAD`."""
        from brain.chat.remember import remember, threads_of
        from brain.chat.thread_store import chat_thread_id

        channel = inbound.event.channel
        where = (
            inbound.conversation.conversation_id
            if inbound.conversation is not None
            else identity_hash(channel, inbound.event.channel_identity)
        )
        try:
            await remember(
                threads_of(self._request.app.state),
                principal_id=person.id,
                thread_id=chat_thread_id(channel, person.id, where),
                channel=channel,
                question=asked.question,
                answered=outcome,
                policies=policies,
                now=now,
            )
        except Exception as exc:
            # The reply still goes out: losing its transcript is no reason to withhold it.
            log.warning("thread.not_kept", error=type(exc).__name__)

    # ------------------------------------------------------------------ the plan

    async def _planned(
        self,
        inbound: Inbound,
        conversation: Conversation,
        person: Principal,
        nominal: EntitlementSet,
        reach: EntitlementSet,
        record: ChannelRecord,
        reply_to: str,
        capabilities: ChannelCapabilities,
        now: datetime,
    ) -> tuple[Outgoing, ...]:
        """A conversation's answer through `plan_delivery`: direct, or at the room's floor."""
        event = inbound.event
        asker = Member(principal_id=person.id, entitlement=reach)
        mine = await self._ask(person, reach, inbound, now, keep=True)
        link = ask_link()
        if not conversation.shared:
            plan = plan_delivery(
                message_of(inbound, conversation),
                members=[asker],
                asker_id=person.id,
                capabilities=capabilities,
                room_body=None,
                asker_body=Rendered(mine.payload, reach.ent_hash()),
                now=now,
            )
            return tuple(
                self._outgoing(mine, reply_to, record, event, person, nominal, capabilities)
                for delivery in plan.deliveries
                if delivery.visibility is Visibility.DIRECT
            )

        present = await self._present(record, conversation)
        members = await self._members(present, inbound, asker, now)
        render = room_plan(members, person.id, capabilities, now=now)
        envelope = render.envelope
        theirs: ChatReply | None = None
        if envelope.grants and not envelope.is_expired(now):
            same = envelope.ent_hash() == reach.ent_hash()
            theirs = mine if same else await self._ask(person, envelope, inbound, now)
            if render.aside_for and not theirs.answered:
                theirs = None
        plan = plan_delivery(
            message_of(inbound, conversation),
            members=members,
            asker_id=person.id,
            capabilities=capabilities,
            room_body=None if theirs is None else Rendered(theirs.payload, envelope.ent_hash()),
            asker_body=Rendered(mine.payload, reach.ent_hash()),
            now=now,
            link=link,
        )
        deliveries = plan.deliveries
        room = [one for one in deliveries if one.visibility is Visibility.ROOM]
        if room and not await self._room_unchanged(
            record, conversation, render, inbound, asker, now
        ):
            deliveries = tuple(one for one in deliveries if one.visibility is not Visibility.ROOM)
        out: list[Outgoing] = []
        for delivery in deliveries:
            if delivery.visibility is Visibility.ROOM and theirs is not None:
                # The room's posting never offers a mark, even when it is the asker's own answer
                # because everybody present holds the same: see `brain.channels.marks`.
                to, reply = conversation.room_to, replace(theirs, trace_id="")
            elif delivery.visibility is Visibility.EPHEMERAL:
                to, reply = conversation.aside_to, mine
            else:
                continue
            out.append(self._outgoing(reply, to, record, event, person, nominal, capabilities))
        if (plan.link or not out) and link:
            # Its own intent, since a room posting may already be going to the same address.
            link_told = LINK_TOLD + link
            out.append(self._sentence(record, event, conversation.room_to, link_told, part="link"))
        return tuple(out)

    async def _room_unchanged(
        self,
        record: ChannelRecord,
        conversation: Conversation,
        render: RoomRender,
        inbound: Inbound,
        asker: Member,
        now: datetime,
    ) -> bool:
        """Whether the room is still the one its posting was made for (M10.4.4).

        Read again, and compared twice: by who is present, through `room.revalidate`, and by the
        floor they make, because a grant revoked meanwhile moves the floor with nobody joining.
        """
        again = await self._present(record, conversation)
        fresh = await self._members(again, inbound, asker, now)
        try:
            revalidate(render, frozenset(one.principal_id for one in fresh), fresh)
        except RoomRefusedError:
            log.info("chat room changed before its answer was sent", channel=record.channel.value)
            return False
        return floor(fresh).ent_hash() == render.envelope.ent_hash()

    # ------------------------------------------------------------------ the room

    async def _present(
        self, record: ChannelRecord, conversation: Conversation
    ) -> frozenset[str] | None:
        """The digests of everybody in the conversation, or None when it cannot be read whole.

        The bot the record names is not a reader: it is the one sending. Lark leaves bots out of
        its list and Slack lists the app's own bot user among the members, so the digest of the
        record's `BOT_ID` is taken out here, for every channel alike, rather than counted as a
        person bound to nobody, which would make every room's floor nothing.
        """
        # Typed as an object: whether a wire can read a room is a question about its class.
        wire: object = channel_wires().get(record.channel)
        if not isinstance(wire, RoomReader):
            return None
        try:
            secret = await asyncio.to_thread(self._secrets.read, record.secret)
        except ChannelSecretsUnavailableError:
            return None
        if secret is None:
            return None
        found: set[str] = set()
        page = ""
        for _ in range(MAX_MEMBER_PAGES):
            try:
                request = wire.members_request(
                    conversation_id=conversation.conversation_id,
                    page=page,
                    secret=secret,
                    tenant=record.tenant,
                )
                answer = await asyncio.to_thread(self._transport.read, request)
                digests, page = wire.members_page(answer)
            except ValueError:
                log.info("chat room not read", channel=record.channel.value)
                return None
            found |= digests
            if len(found) > MAX_ROOM_MEMBERS:
                return None
            if not page:
                bot = record.tenant.get(BOT_ID, "")
                return frozenset(found - {identity_hash(record.channel, bot)} if bot else found)
        return None

    async def _members(
        self, present: frozenset[str] | None, inbound: Inbound, asker: Member, now: datetime
    ) -> list[Member]:
        """Everybody present, each at the reach they hold on this channel, the asker first.

        `present` None, or a list the asker is not on, is a room that could not be read whole: one
        stand-in for everybody unknown, holding nothing, so its floor is nothing.
        """
        channel = inbound.event.channel
        mine = identity_hash(channel, inbound.event.channel_identity)
        if present is None or mine not in present:
            unknown = f"{UNBOUND_MEMBER}room"
            return [asker, Member(unknown, EntitlementSet(principal_id=unknown))]
        people = people_of(self._request)
        members = [asker]
        for digest in sorted(present - {mine}):
            members.append(await self._member(digest, channel, people, asker, now))
        return members

    async def _member(
        self, digest: str, channel: Channel, people: People, asker: Member, now: datetime
    ) -> Member:
        stand_in = f"{UNBOUND_MEMBER}{digest[:24]}"
        binding = await self._bindings.binding_for(channel, digest)
        someone = None if binding is None else await people.live(binding.principal_id)
        if someone is None or not someone.is_active(now) or someone.id == asker.principal_id:
            return Member(stand_in, EntitlementSet(principal_id=stand_in))
        nominal = await self._nominal(someone.id, now)
        return Member(someone.id, admit(nominal, channel, Assurance.BOUND))

    # ------------------------------------------------------------------ the messages

    def _outgoing(
        self,
        reply: ChatReply,
        to: str,
        record: ChannelRecord,
        event: ChannelEvent,
        person: Principal,
        nominal: EntitlementSet,
        capabilities: ChannelCapabilities,
    ) -> Outgoing:
        """One answer to one address, held to the asker's reach when it leaves, or the link where
        the answer holds more than this channel may carry. The asker's own answer ends with the
        line that marks it (M16.6.4)."""
        if not capabilities.may_carry(reply.highest):
            return self._sentence(record, event, to, CEILING_TOLD + (ask_link() or "the console"))
        text = f"{reply.text}\n\n{mark_line(reply.trace_id)}" if reply.trace_id else reply.text
        return Outgoing(
            channel=event.channel,
            to=to,
            intent=reply_intent(record, event),
            text=text,
            payload=reply.payload,
            highest=reply.highest,
            recipient=person.id,
            planned_hash=nominal.ent_hash(),
        )

    def _sentence(
        self, record: ChannelRecord, event: ChannelEvent, to: str, told: str, *, part: str = ""
    ) -> Outgoing:
        """A product sentence to one address: nothing from the company's data in it. `part` keys
        a second message to an address the reply already sends to, so the ledger sends both."""
        intent = reply_intent(record, event)
        if part:
            intent = Intent(
                principal_id=intent.principal_id, intent_ref=f"{intent.intent_ref}.{part}"
            )
        return Outgoing(channel=event.channel, to=to, intent=intent, text=told)
