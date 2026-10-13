"""A person's own settings, read and written as the person (`0229`).

`StoredPreferences.of` reads every setting one person has, for the sender about to write to them or
for the person's own page; `set` and `clear` write as the person, because `0229`'s policies hold an
insert, an update and a delete to the person the transaction names. No function here takes a person
to write as other than the one it names, so there is no way through this module to set somebody
else's preference, and no route reads another person's.

**A read of many people is one statement.** `of_many` answers a sender that is about to write to a
list, so the digest loop does not ask the database once per person.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member.preferences import PreferenceKey, Preferences, parse
from brain.tables.member_preference import MemberPreferenceRow


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


async def preferences_in(
    session: AsyncSession, principal_ids: Collection[str]
) -> dict[str, Preferences]:
    """The settings of each of these people, in the session the caller holds. A person with none
    is given the defaults, so every id asked about is in the answer."""
    ids = sorted(set(principal_ids))
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                MemberPreferenceRow.principal_id, MemberPreferenceRow.key, MemberPreferenceRow.value
            ).where(MemberPreferenceRow.principal_id.in_(ids))
        )
    ).all()
    stored: dict[str, dict[str, Any]] = {one: {} for one in ids}
    for principal, key, value in rows:
        stored[principal][key] = value
    return {one: parse(one, stored[one]) for one in ids}


class StoredPreferences:
    """`auth.member_preference` read and written."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def of_many(self, principal_ids: Collection[str]) -> Mapping[str, Preferences]:
        """The settings of each of these people."""
        async with self._sessions() as session, session.begin():
            return await preferences_in(session, principal_ids)

    async def of(self, principal_id: str) -> Preferences:
        """One person's settings."""
        return (await self.of_many([principal_id]))[principal_id]

    async def set(
        self, principal_id: str, key: PreferenceKey, value: Mapping[str, Any], *, now: datetime
    ) -> None:
        """Keep one setting as this person. One row for the key, replaced when it is set again."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(principal_id))
            statement = pg_insert(MemberPreferenceRow).values(
                principal_id=principal_id, key=key.value, value=dict(value), updated_at=now
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["principal_id", "key"],
                    set_={
                        "value": statement.excluded.value,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
            )

    async def clear(self, principal_id: str, key: PreferenceKey) -> None:
        """Take one setting away as this person, so the default is what is read next."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(principal_id))
            await session.execute(
                delete(MemberPreferenceRow).where(
                    MemberPreferenceRow.principal_id == principal_id,
                    MemberPreferenceRow.key == key.value,
                )
            )
