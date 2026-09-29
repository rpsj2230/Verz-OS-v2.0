"""The rows behind stewardship: who stewards each source, the grants people made to themselves.

`brain.identity.stewardship` decides which self-grant a steward is told of, and
`brain.stewardship_routes` and `brain.connector_routes` ask who may see or change what before this
is reached. This holds the SQL between them and decides nothing, for the split CLAUDE.md names.

**A source's steward is the one named last, and otherwise the data steward, and otherwise whoever
connected it.** `ops.connector_steward` (`0167`) holds every naming. A source nobody has named
anybody for is stewarded by the install's data steward, because
`brain.identity.data_steward.DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD` already makes that person the
one every read of a connected source begins with; on an install that has not appointed one, by the
person who connected it, who is the only other person the record names. See
`A_SOURCE_IS_STEWARDED_FROM_THE_MOMENT_IT_IS_CONNECTED`.

**Naming a steward is one insert, attributed, and the database appends its ledger entry.** The
transaction is told who is acting before the row, and `0167`'s policy refuses a row whose `named_by`
is not that person.

**Self-grants are read as the database recorded them**, including grants retired since, because the
row is the record and the grant's own row is hidden from the application once retired.

Task ids: M7.7.2
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.identity.data_steward import steward_in
from brain.identity.stewardship import SelfGrant
from brain.knowledge.lifecycle import Authority, StoredItem
from brain.knowledge.lifecycle_store import as_person, live_items
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.stewardship import ConnectorStewardRow, SelfGrantRow

#: Why an unnamed source already has a steward.
A_SOURCE_IS_STEWARDED_FROM_THE_MOMENT_IT_IS_CONNECTED: Final = (
    "A source is somebody's to answer for from the moment it is connected, or a grant reaching it "
    "made before anybody was named would be told to nobody. The data steward is the person every "
    "read of a connected source already begins with, so an unnamed source is theirs; on an install "
    "with no data steward it is the person who connected it."
)

#: The most self-grants one steward's list is assembled from. A resource bound, never a permission.
MAX_SELF_GRANTS: Final = 500

#: The most agents one steward's list is assembled from.
MAX_AGENTS: Final = 500


@dataclass(frozen=True)
class NamedSteward:
    """One naming of a source's steward: who, by whom and when."""

    connector: str
    steward_id: str
    named_by: str
    named_at: datetime


def source_steward(
    connector: str,
    *,
    named: Mapping[str, NamedSteward],
    data_steward: str | None,
    connected_by: str,
) -> str:
    """Who stewards this source. See `A_SOURCE_IS_STEWARDED_FROM_THE_MOMENT_IT_IS_CONNECTED`."""
    found = named.get(connector)
    if found is not None:
        return found.steward_id
    return data_steward or connected_by


def self_grant_of(row: SelfGrantRow) -> SelfGrant:
    """One `gate.self_grant` row as the value `brain.identity.stewardship` judges."""
    return SelfGrant(
        grant_id=str(row.grant_id),
        principal_id=row.principal_id,
        capabilities=tuple(Capability(value=one) for one in row.capabilities),
        scope=Scope.model_validate(row.scope),
        at=row.at,
        pack=row.pack,
    )


class StoredStewardship:
    """`ops.connector_steward`, `gate.self_grant` and the stewarded rows, as the app role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def named_stewards(self) -> dict[str, NamedSteward]:
        """The steward named last for each source, by source."""
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ConnectorStewardRow).order_by(
                            ConnectorStewardRow.named_at, ConnectorStewardRow.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        found: dict[str, NamedSteward] = {}
        for row in rows:
            found[row.connector] = NamedSteward(
                connector=row.connector,
                steward_id=row.steward_id,
                named_by=row.named_by,
                named_at=row.named_at,
            )
        return found

    async def data_steward(self) -> str | None:
        """The install's appointed data steward, or None."""
        async with self._sessions() as session:
            return await steward_in(session)

    async def name(
        self, connector: str, steward_id: str, *, by: str, ent_hash: str, trace_id: str
    ) -> NamedSteward:
        """Name this source's steward, attributed to `by`; the database appends the entry."""
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            row = ConnectorStewardRow(connector=connector, steward_id=steward_id, named_by=by)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return NamedSteward(
                connector=row.connector,
                steward_id=row.steward_id,
                named_by=row.named_by,
                named_at=row.named_at,
            )

    async def self_grants(
        self, since: datetime, *, limit: int = MAX_SELF_GRANTS
    ) -> tuple[SelfGrant, ...]:
        """Every grant somebody made to themselves since `since`, newest first."""
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(SelfGrantRow)
                        .where(SelfGrantRow.at >= since)
                        .order_by(SelfGrantRow.at.desc(), SelfGrantRow.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(self_grant_of(row) for row in rows)

    async def documents_stewarded(
        self, principal_id: str, authority: Authority
    ) -> tuple[StoredItem, ...]:
        """The live documents this person stewards, as far as their own reach reads them."""
        async with self._sessions() as session, session.begin():
            await as_person(session, authority)
            found = await live_items(session)
        return tuple(one for one in found if one.owner_id == principal_id)

    async def agents_stewarded(
        self, principal_id: str, *, limit: int = MAX_AGENTS
    ) -> Sequence[AgentRow]:
        """The agents this person stewards that are not archived, as stored rows."""
        async with self._sessions() as session:
            return (
                (
                    await session.execute(
                        select(AgentRow)
                        .where(AgentRow.owner_id == principal_id, AgentRow.archived_at.is_(None))
                        .order_by(AgentRow.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
