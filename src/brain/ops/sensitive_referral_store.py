"""An intercepted question routed to the named person for its topic, recorded without its content.

`brain.audit.compliance.intercept` decides; this is where the decision goes (M24.2.2). The owner's
sentence has three parts and each is one thing here:

- **intercepted before any agent answers**: `brain.api_routes.answer` asks `intercept` first and,
  for a sensitive question, calls `refer` and hands the lane the referral instead of the question;
- **routed to the named person for that topic**: `sensitive_route.<topic>` in `ops.setting`, one
  principal per topic, named from the Compliance screen through `name`, which `0059`'s trigger
  records as a `setting` entry without the value. `refer` reads it in the transaction that files
  the referral, so the row names who it went to at the moment it went;
- **recorded without its content**: `ops.sensitive_referral` holds the asker, the instant, the
  topic and the person, and there is no parameter anywhere in this module through which the
  question could arrive. `THE_QUESTION_HAS_NO_WAY_IN` is the rule and a test reads the signatures.

**Who may read a referral is the database's decision, not this module's.** `0104`'s policy admits
the person it was routed to, or, while nobody was named for its topic when it arrived, whoever is
named now, so a referral filed on an install that had not yet named anybody is not lost. Anybody
else reaches only `tally`, which is counts per topic and month through a function that returns
no row, and `InterceptionTally.report` suppresses those below a cohort.

**The asker's insert writes no row it could read back**, because the asker is not its reader: the
id is minted here and the statement carries no RETURNING, which a policy the asker fails would
refuse.

Task ids: M24.2.2
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from sqlalchemy import TextClause, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.compliance import InterceptionTally, SensitiveTopic
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.audit import attributed_to
from brain.tables.compliance import SensitiveReferralRow
from brain.tables.config import SettingRow, SettingType
from brain.tables.identity import PrincipalRow

#: The `ops.setting` namespace the named people live under, one key per topic.
ROUTE_NAMESPACE: Final = "sensitive_route"

#: The product sentence a named person's row carries, identical on every install.
ROUTE_DESCRIPTION: Final = (
    "The person a question on this sensitive topic is routed to, instead of being answered."
)

#: How many referrals one person's list shows, newest first.
REFERRALS_SHOWN: Final = 100

#: Why no function here takes the question.
THE_QUESTION_HAS_NO_WAY_IN: Final = (
    "The owner asked for a sensitive question to be recorded without its content. So no function "
    "in this module has a parameter a question could be passed through: refer takes the asker, "
    "the topic and the request's attribution, and a test reads every signature for a text "
    "argument. A column that could hold it would be filled by the first caller who thought it "
    "would help the person following up."
)


def route_key(topic: SensitiveTopic) -> str:
    """`sensitive_route.<topic>`, the key the named person for `topic` is kept under."""
    return f"{ROUTE_NAMESPACE}.{topic.value}"


@dataclass(frozen=True)
class NamedPerson:
    """Who a topic is routed to, and who named them, when."""

    topic: SensitiveTopic
    principal_id: str
    named_by: str
    named_at: datetime


@dataclass(frozen=True)
class Referral:
    """One referral as its reader sees it. Never anything that was said."""

    referral_id: str
    topic: SensitiveTopic
    asked_by: str
    asked_at: datetime
    routed_to: str | None
    handled_at: datetime | None
    handled_by: str | None


class NamingRefusedError(Exception):
    """A named person who is not a live principal on this install."""


@runtime_checkable
class SensitiveReferrals(Protocol):
    """Filing, routing, reading and handling referrals."""

    async def refer(
        self, *, asked_by: str, topic: SensitiveTopic, ent_hash: str, trace_id: str
    ) -> str | None: ...

    async def named(self) -> Mapping[SensitiveTopic, NamedPerson]: ...

    async def name(
        self, topic: SensitiveTopic, principal_id: str, *, by: str, ent_hash: str, trace_id: str
    ) -> NamedPerson: ...

    async def mine(self, principal_id: str) -> tuple[Referral, ...]: ...

    async def handle(
        self, referral_id: str, *, by: str, ent_hash: str, trace_id: str, at: datetime
    ) -> bool: ...

    async def tally(self, period: str) -> InterceptionTally: ...


def named_from(states: Mapping[str, SettingState]) -> dict[SensitiveTopic, NamedPerson]:
    """The named people among a namespace read, by topic. A key naming no topic is ignored."""
    topics = {topic.value: topic for topic in SensitiveTopic}
    found: dict[SensitiveTopic, NamedPerson] = {}
    for name, state in values_under(states, ROUTE_NAMESPACE).items():
        topic = topics.get(name)
        if topic is not None and isinstance(state.value, str) and state.value:
            found[topic] = NamedPerson(
                topic=topic,
                principal_id=state.value,
                named_by=state.updated_by,
                named_at=state.updated_at,
            )
    return found


def _setting(name: str, value: str) -> TextClause:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def _attribute(session: AsyncSession, *, actor: str, ent_hash: str, trace_id: str) -> None:
    """The session's principal for the policies, and the attribution for any trigger."""
    await session.execute(_setting(PRINCIPAL_SETTING, actor))
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


def referral_from(row: SensitiveReferralRow) -> Referral:
    return Referral(
        referral_id=str(row.referral_id),
        topic=SensitiveTopic(row.topic),
        asked_by=row.asked_by,
        asked_at=row.asked_at,
        routed_to=row.routed_to,
        handled_at=row.handled_at,
        handled_by=row.handled_by,
    )


class StoredSensitiveReferrals:
    """`ops.sensitive_referral` and the `sensitive_route` settings, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def refer(
        self, *, asked_by: str, topic: SensitiveTopic, ent_hash: str, trace_id: str
    ) -> str | None:
        """File one referral, routed to whoever is named for `topic` now. Returns who, or None."""
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor=asked_by, ent_hash=ent_hash, trace_id=trace_id)
            named = await session.scalar(
                select(SettingRow.value)
                .where(SettingRow.key == route_key(topic))
                .where(SettingRow.deleted_at.is_(None))
            )
            routed_to = named if isinstance(named, str) and named else None
            await session.execute(
                insert(SensitiveReferralRow).values(
                    referral_id=uuid.uuid4(),
                    topic=topic.value,
                    asked_by=asked_by,
                    routed_to=routed_to,
                )
            )
        return routed_to

    async def named(self) -> Mapping[SensitiveTopic, NamedPerson]:
        async with self._sessions() as session, session.begin():
            return named_from(await read_namespace(session, ROUTE_NAMESPACE))

    async def name(
        self, topic: SensitiveTopic, principal_id: str, *, by: str, ent_hash: str, trace_id: str
    ) -> NamedPerson:
        """Name the person for `topic`. Refused for somebody who is not a live principal here."""
        async with self._sessions() as session, session.begin():
            live = await session.scalar(
                select(func.count())
                .select_from(PrincipalRow)
                .where(PrincipalRow.id == principal_id)
                .where(PrincipalRow.disabled_at.is_(None))
            )
            if not live:
                raise NamingRefusedError(principal_id)
            await _attribute(session, actor=by, ent_hash=ent_hash, trace_id=trace_id)
            await put(
                session,
                route_key(topic),
                value_type=SettingType.STRING,
                value=principal_id,
                description=ROUTE_DESCRIPTION,
                updated_by=by,
            )
            states = await read_namespace(session, ROUTE_NAMESPACE)
        return named_from(states)[topic]

    async def mine(self, principal_id: str) -> tuple[Referral, ...]:
        """The referrals this session's policy admits, newest first."""
        async with self._sessions() as session, session.begin():
            await session.execute(_setting(PRINCIPAL_SETTING, principal_id))
            rows = (
                (
                    await session.execute(
                        select(SensitiveReferralRow)
                        .order_by(
                            SensitiveReferralRow.asked_at.desc(), SensitiveReferralRow.referral_id
                        )
                        .limit(REFERRALS_SHOWN)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(referral_from(row) for row in rows)

    async def handle(
        self, referral_id: str, *, by: str, ent_hash: str, trace_id: str, at: datetime
    ) -> bool:
        """Mark a referral handled, taking it over when it was routed to nobody. False when this
        session's policy does not admit it or it was handled already."""
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor=by, ent_hash=ent_hash, trace_id=trace_id)
            done = await session.execute(
                update(SensitiveReferralRow)
                .where(SensitiveReferralRow.referral_id == uuid.UUID(referral_id))
                .where(SensitiveReferralRow.handled_at.is_(None))
                .where(
                    or_(
                        SensitiveReferralRow.routed_to == by,
                        SensitiveReferralRow.routed_to.is_(None),
                    )
                )
                .values(routed_to=by, handled_at=at, handled_by=by)
            )
            return bool(done.rowcount)  # type: ignore[attr-defined]

    async def tally(self, period: str) -> InterceptionTally:
        """One month's counts per topic, from the function that returns no row."""
        async with self._sessions() as session, session.begin():
            found = await session.execute(
                text(
                    "SELECT topic, referrals FROM ops.sensitive_referral_tally(:period)"
                ).bindparams(period=period)
            )
            counts = {SensitiveTopic(str(topic)): int(n) for topic, n in found.all()}
        return InterceptionTally(period=period, counts=counts)
