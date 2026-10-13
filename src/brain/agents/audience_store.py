"""Who an agent is offered to beside its level: the store behind `agent.audience_extra` (M13.8.19).

`brain.agents.model` says what an added department or person is (`AgentAudience.extra_*`) and that
it is discovery only. This reads and writes the rows, in the session's own name, and hands the
roster the extras to put on a record. It decides nothing about who may add: the caller asks the
lifecycle authority over the agent, and this takes the person as a value.

**Reading is one question for every agent at once**, `extras_of`, so a roster costs one statement
and not one per agent, and an agent with none is simply absent from the answer.

**Adding what is there is a no-op and removing what is not is a refusal to say so.** A second add
of a live name returns the first row's id, and a removal of a name that is not live returns False,
which a route answers as it answers an agent that is not there.

Task ids: M13.8.19
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.audience_extra import AudienceExtraRow, ExtraKind

#: Said when a name is not a department or a person.
NOT_A_NAME: Final = "a department or a person is named by one word with no spaces in it"


@dataclass(frozen=True)
class Extras:
    """The live departments and people one agent is offered to, sorted."""

    departments: tuple[str, ...] = ()
    people: tuple[str, ...] = ()


async def _as(session: AsyncSession, principal: str) -> None:
    await session.execute(
        text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
    )


async def extras_of(session: AsyncSession) -> Mapping[str, Extras]:
    """Every agent's live extras, by agent id. An agent with none is not a key."""
    rows = (
        await session.execute(
            select(AudienceExtraRow.agent_id, AudienceExtraRow.kind, AudienceExtraRow.value)
            .where(AudienceExtraRow.removed_at.is_(None))
            .order_by(AudienceExtraRow.agent_id, AudienceExtraRow.value)
        )
    ).all()
    departments: dict[str, list[str]] = {}
    people: dict[str, list[str]] = {}
    for agent_id, kind, value in rows:
        (departments if kind == ExtraKind.DEPARTMENT.value else people).setdefault(
            agent_id, []
        ).append(value)
    return {
        one: Extras(tuple(departments.get(one, ())), tuple(people.get(one, ())))
        for one in sorted({*departments, *people})
    }


async def add_extra(
    session: AsyncSession, *, agent_id: str, kind: ExtraKind, value: str, by: str
) -> uuid.UUID:
    """Offer an agent to one more department or person, in the adder's own name."""
    if not value or any(one.isspace() for one in value):
        raise ValueError(NOT_A_NAME)
    await _as(session, by)
    live = (
        await session.execute(
            select(AudienceExtraRow.id).where(
                AudienceExtraRow.agent_id == agent_id,
                AudienceExtraRow.kind == kind.value,
                AudienceExtraRow.value == value,
                AudienceExtraRow.removed_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if live is not None:
        return live
    made = AudienceExtraRow(agent_id=agent_id, kind=kind.value, value=value, added_by=by)
    session.add(made)
    await session.flush()
    return made.id


async def remove_extra(
    session: AsyncSession, *, agent_id: str, kind: ExtraKind, value: str, by: str
) -> bool:
    """Withdraw an offer, in the remover's own name. False when there was none live."""
    await _as(session, by)
    done = await session.execute(
        update(AudienceExtraRow)
        .where(
            AudienceExtraRow.agent_id == agent_id,
            AudienceExtraRow.kind == kind.value,
            AudienceExtraRow.value == value,
            AudienceExtraRow.removed_at.is_(None),
        )
        .values(removed_by=by, removed_at=text("statement_timestamp()"))
        .returning(AudienceExtraRow.id)
    )
    return done.first() is not None
