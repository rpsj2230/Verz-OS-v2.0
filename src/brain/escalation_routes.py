"""A question nothing answered, handed to a named person in their own channel, and the lists of it.

Three things arrive here, and each is the wiring of something `brain.gate.escalating` and
`brain.ops.escalation_store` already decide.

**The answer path hands an abstention on (M8.3.1, M8.3.2).** `escalated` runs in
`brain.api_routes.answered_for` after the lane, for the web and every chat channel alike. When the
answer abstained, the agent asked was a stored one, and one of the skills it runs with (pinned,
approved, unmoved and within the run's reach, `brain.gate.model_lane.skills_offered`) declares a
queue, the handoff is filed and sent, and the asker is told one sentence naming the queue and
nothing about a person. It fires on every abstention alike, so a question the asker was refused and
one with nothing behind it are handed on identically and read identically, which is
`brain.gate.escalating.A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE` kept at the asker's end too.
A failure to file one never fails the answer: the asker still gets the abstention, which is true,
and the log says the handoff was not made.

**It is sent while the asker waits, from the application, and never by the worker.** The channel's
secret is the application's to borrow (`ops/openbao/policies/application.hcl`) and not the
worker's, so the send is `brain.channels.outbound.deliver` on this request, with the channel's
record read at send time, the notice's switch asked first (`brain.ops.notices.notice_is_on`), and
the outcome written to the row. A delivery that was refused, or a queue nobody was named for yet,
leaves the handoff on the named person's list here, where whoever is named later finds it.
Rejected: a worker that sends queued handoffs, which would need the worker to hold every channel's
secret for this one purpose.

**Two lists, and the naming form.** `GET /escalations` is the caller's own: what they asked that
was handed on, with the sentence they are told (which changes once the worker's
`escalation_expiry` marks it expired), and what was handed to them. `GET` and `PUT
/govern/escalation-routes` name who answers for each queue and where they are reached, asked of the
Compliance screen's authority, because routing a question to a named person instead of answering
it is the same decision as a sensitive topic's.

Task ids: M8.3.1, M8.3.2, M8.3.4
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Answering, Asked
from brain.channels.adapter import channel_wires
from brain.compliance_routes import may_govern_compliance
from brain.core.errors import Absent
from brain.gate.abstain import EscalationRoute
from brain.gate.context import Channel
from brain.gate.escalating import (
    declared_by,
    escalation_for,
    handoff_text,
    said_to_asker,
)
from brain.gate.streaming import Event, encode
from brain.ops.escalation_store import (
    Filed,
    KeptEscalation,
    NamedRoute,
    NamingRefusedError,
    StoredEscalations,
)
from brain.people_names import names_for
from brain.routing_routes import sessions_of
from brain.tables.escalation import EscalationDelivery
from brain.tables.skill import ESCALATION_QUEUE_PATTERN

if TYPE_CHECKING:
    from brain.agents.model import AgentRecord
    from brain.core.entitlement import EntitlementSet
    from brain.gate.abstain import Escalation
    from brain.gate.answer import Answered
    from brain.tools.skills import ImportedSkill

log = structlog.get_logger()

ESCALATIONS_PATH: Final = "/escalations"
ROUTES_PATH: Final = "/govern/escalation-routes"
ROUTE_PATH: Final = ROUTES_PATH + "/{queue}"

#: The longest address a route may name on its channel: a chat id, a mailbox, a webhook's name.
ADDRESS_CHARS: Final = 200

#: What the caller's list says above it.
TOLD: Final = (
    "Questions nothing answered that were handed to a person. What you asked shows what you were "
    "told; what was handed to you shows the question in the asker's words and what is needed."
)

#: What the naming screen says above the queues.
ROUTING_TOLD: Final = (
    "A skill names a queue for the questions it could not answer. Name who answers for each queue "
    "and where they are reached; a question handed to a queue nobody answers for waits for "
    "whoever is named next."
)

#: What a naming refused for the person says. One sentence for somebody who is not here and
#: somebody disabled, so the form does not tell who exists.
NOT_NAMEABLE: Final = "the person named is not somebody active on this install"

router = APIRouter(prefix=API_PREFIX, tags=["escalation"])


# ------------------------------------------------------------------------ the wiring
def escalations_of(request: Request) -> StoredEscalations | None:
    """`app.state.escalations` when something put one there, or the database, or None."""
    found = getattr(request.app.state, "escalations", None)
    if isinstance(found, StoredEscalations):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredEscalations(sessions)


def sendable() -> tuple[Channel, ...]:
    """The channels a handoff can be sent on: those with a wire, in a stable order."""
    return tuple(sorted(channel_wires(), key=lambda one: one.value))


async def offered_skills(
    request: Request, agent: AgentRecord, *, caller: EntitlementSet, now: datetime
) -> tuple[ImportedSkill, ...]:
    """The skills this agent runs with for this caller: the run `/answer` builds, through
    `brain.api_routes.agent_run_of`, so an escalation and an answer read one set of pins."""
    from brain.api_routes import agent_run_of
    from brain.gate.model_lane import skills_offered
    from brain.tools.registry import ToolRegistry

    registry = getattr(request.app.state, "tools", None)
    if sessions_of(request) is None or not isinstance(registry, ToolRegistry):
        return ()
    run = await agent_run_of(request.app.state, agent, registry)
    if run is None or not run.pins:
        return ()
    return skills_offered(run, caller=caller, now=now)


def with_sentence(answered: Answered, sentence: str) -> Answered:
    """The answer with one more sentence before its `done` frame, as a text channel joins them."""
    if not answered.frames:
        return answered
    told = encode(Event.TEXT, f" {sentence}")
    return dataclasses.replace(answered, frames=(*answered.frames[:-1], told, answered.frames[-1]))


async def handed_on(
    request: Request, filed: Filed, escalation: Escalation, *, asker: str, now: datetime
) -> EscalationDelivery:
    """Send the handoff to the named person's channel, and say how it went.

    The notice's switch first, then `brain.channels.outbound.deliver` with the channel's record
    read now. A message for nobody in particular as `deliver` defines one: it carries the asker's
    own words and nothing from the company's data, so there is no recipient reach to hold it to.
    """
    from brain.channel_routes import (
        deliveries_of,
        ledger_of,
        reach_of,
        records_of,
        secrets_of,
        transport_of,
    )
    from brain.channels.outbound import Outgoing, deliver
    from brain.ops.idempotency import Intent
    from brain.ops.notices import NoticeKind, notice_is_on

    route = filed.route
    sessions = sessions_of(request)
    if route is None or sessions is None:
        return EscalationDelivery.NOT_SENT
    async with sessions() as session:
        if not await notice_is_on(session, NoticeKind.HANDED_TO_A_PERSON):
            return EscalationDelivery.NOT_SENT
    handoff = escalation.handoff
    outgoing = Outgoing(
        channel=route.channel,
        to=route.address,
        intent=Intent(principal_id=route.person, intent_ref=f"escalation.{filed.escalation_id}"),
        text=handoff_text(
            queue=route.queue,
            asker=asker,
            question=handoff.question,
            tried=handoff.tried,
            needed=handoff.needed,
            expires_at=escalation.expires_at,
        ),
    )
    delivered = await deliver(
        outgoing,
        record=await records_of(request).get(route.channel),
        secrets=secrets_of(request),
        reach=reach_of(request),
        transport=transport_of(request),
        ledger=ledger_of(request),
        deliveries=deliveries_of(request),
        now=now,
    )
    return EscalationDelivery(delivered.outcome.value)


async def escalated(
    request: Request,
    answered: Answered,
    *,
    agent: AgentRecord | None,
    asking: Answering,
    question: str,
    trace_id: str,
) -> Answered:
    """The answer, and when it abstained under a skill that declares a queue, the handoff made.

    Returns `answered` unchanged when there is nothing to hand on, and when handing it on failed,
    which is logged: see the module docstring.
    """
    if answered.abstention is None or agent is None:
        return answered
    store = escalations_of(request)
    if store is None:
        return answered
    try:
        skill = declared_by(
            await offered_skills(request, agent, caller=asking.reach, now=asking.now)
        )
        if skill is None:
            return answered
        escalation = escalation_for(
            skill,
            # Where it goes is read when it is filed; this route only carries the queue's name.
            route=EscalationRoute(queue=skill.escalate_to, channel=Channel.CONSOLE),
            asker_id=asking.principal.id,
            question=question,
            trace_ref=trace_id,
            now=asking.now,
        )
        filed = await store.file(
            escalation,
            skill_name=skill.name,
            agent_id=agent.agent_id,
            ent_hash=asking.reach.ent_hash(),
        )
        delivery = await handed_on(
            request, filed, escalation, asker=asking.principal.display_name, now=asking.now
        )
        if filed.route is not None:
            await store.record_delivery(
                filed.escalation_id,
                asker_id=asking.principal.id,
                delivery=delivery,
                at=asking.now,
            )
        log.info("escalated", queue=skill.escalate_to, delivery=delivery.value)
        told = escalation.for_asker().text
    except Exception as exc:
        # Broad, for the reason the answer route gives about its own: whatever a driver or a
        # vendor raises here would otherwise turn a true abstention into a fault.
        log.warning("escalation.not_made", error=type(exc).__name__)
        return answered
    return dataclasses.replace(with_sentence(answered, told), escalated=True)


# ------------------------------------------------------------------------ the views
class AskedView(BaseModel):
    """One question of the caller's that was handed on, and the sentence they are told."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    escalation_id: str
    queue: str
    question: str
    raised_at: datetime
    expires_at: datetime
    expired: bool
    said: str


class HandedView(BaseModel):
    """One question handed to the caller: who asked, what, what was tried and what is needed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    escalation_id: str
    queue: str
    asker_id: str
    asker_name: str
    question: str
    tried: list[str]
    needed: str
    raised_at: datetime
    expires_at: datetime
    expired: bool


class EscalationsView(BaseModel):
    """The caller's own two lists, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    asked: list[AskedView]
    handed: list[HandedView]
    told: str


class RouteView(BaseModel):
    """Who answers for one queue and where they are reached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    queue: str
    person: str
    person_name: str
    channel: str
    address: str
    named_by: str
    named_at: datetime


class RoutesView(BaseModel):
    """Every named queue, the channels a handoff can be sent on, and the screen's sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    routes: list[RouteView]
    channels: list[str]
    told: str


class RouteBody(BaseModel):
    """Who answers for a queue and where: the person, their channel and their address on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person: str = Field(min_length=1, max_length=128)
    channel: Channel
    address: str = Field(min_length=1, max_length=ADDRESS_CHARS)


def _is_handed_to(one: KeptEscalation, principal_id: str) -> bool:
    """Whether the caller reads this row as the person it was handed to.

    Routed to them, or routed to nobody and not theirs: `0168`'s policy admits a row routed to
    nobody only to the asker and to whoever is named for its queue now, so the second is them.
    """
    if one.routed_to == principal_id:
        return True
    return one.routed_to is None and one.asker_id != principal_id


def route_view(route: NamedRoute, names: dict[str, str]) -> RouteView:
    return RouteView(
        queue=route.queue,
        person=route.person,
        person_name=names.get(route.person, ""),
        channel=route.channel.value,
        address=route.address,
        named_by=route.named_by,
        named_at=route.named_at,
    )


def _refused() -> Absent:
    return Absent("the escalation routes are not answerable for this caller")


def _store(request: Request) -> StoredEscalations:
    found = escalations_of(request)
    if found is None:
        raise Absent("no escalations on this process")
    return found


# ------------------------------------------------------------------------ the routes
@router.get(ESCALATIONS_PATH, response_model=EscalationsView, responses=COMMON_RESPONSES)
async def my_escalations(request: Request, asked: Asked) -> EscalationsView:
    """What the caller asked that was handed on, and what was handed to them (M8.3.2, M8.3.4)."""
    me = asked.caller.principal.id
    found = await _store(request).mine(me)
    handed = [one for one in found if _is_handed_to(one, me)]
    names = await names_for(request, {one.asker_id for one in handed})
    return EscalationsView(
        asked=[
            AskedView(
                escalation_id=one.escalation_id,
                queue=one.queue,
                question=one.question,
                raised_at=one.raised_at,
                expires_at=one.expires_at,
                expired=one.expired_at is not None,
                said=said_to_asker(one.queue, expired=one.expired_at is not None),
            )
            for one in found
            if one.asker_id == me
        ],
        handed=[
            HandedView(
                escalation_id=one.escalation_id,
                queue=one.queue,
                asker_id=one.asker_id,
                asker_name=names.get(one.asker_id, ""),
                question=one.question,
                tried=list(one.tried),
                needed=one.needed,
                raised_at=one.raised_at,
                expires_at=one.expires_at,
                expired=one.expired_at is not None,
            )
            for one in handed
        ],
        told=TOLD,
    )


@router.get(ROUTES_PATH, response_model=RoutesView, responses=COMMON_RESPONSES)
async def escalation_routes(request: Request, asked: Asked) -> RoutesView:
    """Every named queue and where it is reached. The Compliance screen's authority."""
    if not may_govern_compliance(asked.reach, asked.now):
        raise _refused()
    routes = await _store(request).routes()
    names = await names_for(request, {one.person for one in routes.values()})
    return RoutesView(
        routes=[route_view(routes[queue], names) for queue in sorted(routes)],
        channels=[one.value for one in sendable()],
        told=ROUTING_TOLD,
    )


@router.put(ROUTE_PATH, response_model=RouteView, responses=COMMON_RESPONSES)
async def name_route(
    request: Request,
    queue: Annotated[str, Path(pattern=ESCALATION_QUEUE_PATTERN, max_length=60)],
    body: RouteBody,
    asked: Asked,
) -> RouteView:
    """Name who answers for `queue` and where. `0059`'s trigger records it, not the value."""
    if not may_govern_compliance(asked.reach, asked.now):
        raise _refused()
    if body.channel not in sendable():
        message = "that was not recorded: nothing can be sent on that channel"
        raise Absent(message, public_message=message)
    try:
        named = await _store(request).name_route(
            queue,
            body.person,
            body.channel,
            body.address.strip(),
            by=asked.reach.principal_id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=str(structlog.contextvars.get_contextvars().get("trace_id", "")) or "untraced",
        )
    except NamingRefusedError:
        message = f"that was not recorded: {NOT_NAMEABLE}"
        raise Absent(message, public_message=message) from None
    names = await names_for(request, {named.person})
    return route_view(named, names)
