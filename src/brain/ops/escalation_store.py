"""The rows behind escalation: who answers for each queue, each handoff, and when it expired.

`brain.gate.escalating` decides which skill escalates and what the handoff says, and
`brain.escalation_routes` asks who may name a queue's person before this is reached. This holds the
SQL between them and decides nothing, for the split CLAUDE.md names.

**Who answers for a queue is `escalation_route.<queue>` in `ops.setting`**, as the person for a
sensitive topic is `sensitive_route.<topic>` (`brain.ops.sensitive_referral_store`). The value is a
JSON object: the person, the channel they are reached on and their address on it, because the
product stores no chat address for anybody (a binding holds a digest of one), and a route that
reaches a person needs one. `0059`'s trigger records every naming as a `setting` ledger entry
without the value. A person who is not a live principal here is refused, as a topic's is.

**A handoff is filed in the asker's own session and names who it went to at that moment.** The
route is read in the transaction that writes the row, so `routed_to` is the person named when the
question arrived. Nobody named: the row names nobody, and `0168`'s policy lets whoever is named
later read it, which is how a queue named after its first question does not lose that question.

**How the delivery went is recorded by the same person's session, and nothing else is.** `0168`
grants UPDATE on the two delivery columns alone. Expiry is the worker's: `expire_overdue` runs as
the worker's login, which reads past the policies as the knowledge review sweep does, and marks
every open handoff whose deadline has passed.

Task ids: M8.3.2, M8.3.4
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import TextClause, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.abstain import Escalation
from brain.gate.context import Channel
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.session import make_app_engine, make_session_factory
from brain.tables.audit import attributed_to
from brain.tables.config import SettingRow, SettingType
from brain.tables.escalation import EscalationDelivery, EscalationRow
from brain.tables.identity import PrincipalRow

#: The `ops.setting` namespace the named people live under, one key per queue.
ROUTE_NAMESPACE: Final = "escalation_route"

#: The product sentence a queue's row carries, identical on every install.
ROUTE_DESCRIPTION: Final = (
    "The person a question escalated to this queue is handed to, and where they are reached."
)

#: How many handoffs one list shows, newest first.
ESCALATIONS_SHOWN: Final = 100


@dataclass(frozen=True)
class NamedRoute:
    """Who answers for one queue, where they are reached, and who named them, when."""

    queue: str
    person: str
    channel: Channel
    address: str
    named_by: str
    named_at: datetime


@dataclass(frozen=True)
class KeptEscalation:
    """One handoff as its reader sees it."""

    escalation_id: str
    queue: str
    asker_id: str
    question: str
    tried: tuple[str, ...]
    needed: str
    raised_at: datetime
    expires_at: datetime
    routed_to: str | None
    delivery: EscalationDelivery | None
    expired_at: datetime | None


class NamingRefusedError(Exception):
    """A named person who is not a live principal on this install."""


def route_key(queue: str) -> str:
    """`escalation_route.<queue>`, the key the person for `queue` is kept under."""
    return f"{ROUTE_NAMESPACE}.{queue}"


def route_of(queue: str, state: SettingState) -> NamedRoute | None:
    """One row's route, or None for a value that is not one. A malformed row routes nothing."""
    value = state.value
    if not isinstance(value, dict):
        return None
    person, channel, address = value.get("person"), value.get("channel"), value.get("address")
    if not (isinstance(person, str) and person and isinstance(address, str)):
        return None
    try:
        reached_on = Channel(str(channel))
    except ValueError:
        return None
    return NamedRoute(
        queue=queue,
        person=person,
        channel=reached_on,
        address=address,
        named_by=state.updated_by,
        named_at=state.updated_at,
    )


def routes_from(states: Mapping[str, SettingState]) -> dict[str, NamedRoute]:
    """The named routes among a namespace read, by queue."""
    found: dict[str, NamedRoute] = {}
    for queue, state in values_under(states, ROUTE_NAMESPACE).items():
        route = route_of(queue, state)
        if route is not None:
            found[queue] = route
    return found


def route_value(person: str, channel: Channel, address: str) -> dict[str, Any]:
    """What a queue's row holds."""
    return {"person": person, "channel": channel.value, "address": address}


def kept_of(row: EscalationRow) -> KeptEscalation:
    return KeptEscalation(
        escalation_id=str(row.id),
        queue=row.queue,
        asker_id=row.asker_id,
        question=row.question,
        tried=tuple(str(one) for one in row.tried),
        needed=row.needed,
        raised_at=row.raised_at,
        expires_at=row.expires_at,
        routed_to=row.routed_to,
        delivery=None if row.delivery is None else EscalationDelivery(row.delivery),
        expired_at=row.expired_at,
    )


def _setting(name: str, value: str) -> TextClause:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def _attribute(session: AsyncSession, *, actor: str, ent_hash: str, trace_id: str) -> None:
    """The session's principal for the policies, and the attribution for any trigger."""
    await session.execute(_setting(PRINCIPAL_SETTING, actor))
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


@dataclass(frozen=True)
class Filed:
    """A handoff written: its id, and the route it went to, or None when nobody was named."""

    escalation_id: str
    route: NamedRoute | None


class StoredEscalations:
    """`gate.escalation` and the `escalation_route` settings, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def routes(self) -> dict[str, NamedRoute]:
        """Every named queue's route, by queue."""
        async with self._sessions() as session, session.begin():
            return routes_from(await read_namespace(session, ROUTE_NAMESPACE))

    async def name_route(
        self,
        queue: str,
        person: str,
        channel: Channel,
        address: str,
        *,
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> NamedRoute:
        """Name who answers for `queue`. Refused for somebody who is not a live principal here."""
        async with self._sessions() as session, session.begin():
            live = await session.scalar(
                select(func.count())
                .select_from(PrincipalRow)
                .where(PrincipalRow.id == person)
                .where(PrincipalRow.disabled_at.is_(None))
            )
            if not live:
                raise NamingRefusedError(person)
            await _attribute(session, actor=by, ent_hash=ent_hash, trace_id=trace_id)
            await put(
                session,
                route_key(queue),
                value_type=SettingType.JSON,
                value=route_value(person, channel, address),
                description=ROUTE_DESCRIPTION,
                updated_by=by,
            )
            states = await read_namespace(session, ROUTE_NAMESPACE)
        return routes_from(states)[queue]

    async def file(
        self,
        escalation: Escalation,
        *,
        skill_name: str,
        agent_id: str,
        ent_hash: str,
    ) -> Filed:
        """Write one handoff in the asker's session, routed to whoever is named for its queue."""
        handoff = escalation.handoff
        queue = escalation.route.queue
        escalation_id = uuid.uuid4()
        async with self._sessions() as session, session.begin():
            await _attribute(
                session, actor=handoff.asker_id, ent_hash=ent_hash, trace_id=handoff.trace_ref
            )
            named = await session.scalar(
                select(SettingRow.value)
                .where(SettingRow.key == route_key(queue))
                .where(SettingRow.deleted_at.is_(None))
            )
            route = route_of(
                queue,
                SettingState(
                    key=route_key(queue),
                    value_type=SettingType.JSON.value,
                    value=named,
                    updated_by="",
                    updated_at=escalation.raised_at,
                ),
            )
            await session.execute(
                insert(EscalationRow).values(
                    id=escalation_id,
                    trigger=escalation.trigger.value,
                    queue=queue,
                    skill_name=skill_name,
                    agent_id=agent_id,
                    asker_id=handoff.asker_id,
                    question=handoff.question,
                    tried=list(handoff.tried),
                    needed=handoff.needed,
                    trace_ref=handoff.trace_ref,
                    raised_at=escalation.raised_at,
                    expires_at=escalation.expires_at,
                    routed_to=None if route is None else route.person,
                )
            )
        return Filed(escalation_id=str(escalation_id), route=route)

    async def record_delivery(
        self, escalation_id: str, *, asker_id: str, delivery: EscalationDelivery, at: datetime
    ) -> bool:
        """How sending it went, in the asker's session. False once it was recorded already."""
        async with self._sessions() as session, session.begin():
            await session.execute(_setting(PRINCIPAL_SETTING, asker_id))
            done = await session.execute(
                update(EscalationRow)
                .where(EscalationRow.id == uuid.UUID(escalation_id))
                .where(EscalationRow.delivered_at.is_(None))
                .values(delivered_at=at, delivery=delivery.value)
            )
            return bool(done.rowcount)  # type: ignore[attr-defined]

    async def mine(self, principal_id: str) -> tuple[KeptEscalation, ...]:
        """The handoffs this session's policy admits, newest first: asked or routed to them."""
        async with self._sessions() as session, session.begin():
            await session.execute(_setting(PRINCIPAL_SETTING, principal_id))
            rows = (
                (
                    await session.execute(
                        select(EscalationRow)
                        .where(
                            or_(
                                EscalationRow.asker_id == principal_id,
                                EscalationRow.routed_to == principal_id,
                                EscalationRow.routed_to.is_(None),
                            )
                        )
                        .order_by(EscalationRow.raised_at.desc(), EscalationRow.id)
                        .limit(ESCALATIONS_SHOWN)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(kept_of(row) for row in rows)


async def expire_overdue(session: AsyncSession, *, now: datetime) -> int:
    """Mark every open handoff whose deadline has passed as expired now. How many were."""
    done = await session.execute(
        update(EscalationRow)
        .where(EscalationRow.expired_at.is_(None))
        .where(EscalationRow.expires_at <= now)
        .values(expired_at=now)
    )
    return int(done.rowcount)  # type: ignore[attr-defined]


def run_expiry_now(
    database_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> int:
    """`expire_overdue`, from a thread with no event loop of its own, committed.

    The shape `brain.knowledge.item_store.run_reverification_now` takes and for its reasons: the
    worker's schedule runs a control off its event loop, the engine is the application's, and
    which loop psycopg accepts is decided in `brain.ops.worker`.
    """

    async def once() -> int:
        engine = make_app_engine(database_url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                return await expire_overdue(session, now=now)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)
