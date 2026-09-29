"""The display names of the people a governance answer already names by id.

The ledger, an access request and a referral each record a person as a principal id, because an id
is what a trigger or a route has in hand, and the console printed it. An id is how the system names
somebody and never how a colleague does, so the Governance screens could not be read without a
second window open on the directory. Each of those answers now carries the names of the people on
its own rows, read here.

**Only ids the answer already carries are looked up.** A route hands over the ids on the rows it is
about to send, which the reader is shown in any case, so a name says nothing the row did not: it is
the same person, spelled for a person. **Nothing here lists anybody**, and there is no call that
takes no ids. An id that names no principal (a database role a trigger attributed an entry to, or
the system's own account) is absent from the answer, and the screen draws what the row said. See
`A_NAME_IS_LOOKED_UP_ONLY_FOR_AN_ID_THE_ROW_ALREADY_CARRIES`.

Rejected: a join in each route's own statement. Several routes over several stores would carry
several copies of one lookup, and the ledger's rows are loaded before the view decides which of them
this reader may see, so a join there would name people on rows that are then withheld.

Task ids: M27.16.1
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final, Protocol, runtime_checkable

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.routing_routes import sessions_of
from brain.tables.identity import PrincipalRow

#: The most ids one lookup reads. A page of any governance list names fewer people than this.
MOST_NAMES: Final = 500

#: Why an answer names only the people on its own rows.
A_NAME_IS_LOOKED_UP_ONLY_FOR_AN_ID_THE_ROW_ALREADY_CARRIES: Final = (
    "A governance answer names the people on the rows it sends and nobody else, by looking up "
    "exactly the ids those rows carry. The reader is shown each id in any case, so its name tells "
    "them nothing new; a lookup that took no ids, or ids from rows the reader is not shown, would "
    "be a directory handed over through a screen that grants none."
)


@runtime_checkable
class PeopleNames(Protocol):
    """Display names by principal id, for exactly the ids asked about."""

    async def names(self, principal_ids: Collection[str]) -> dict[str, str]:
        """The names of those ids that are principals. An id that is not one is left out."""
        ...


class StoredPeopleNames:
    """`auth.principal`'s display names, read for the ids given and no others."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def names(self, principal_ids: Collection[str]) -> dict[str, str]:
        wanted = sorted(set(principal_ids))[:MOST_NAMES]
        if not wanted:
            return {}
        async with self._sessions() as session:
            found = await session.execute(
                select(PrincipalRow.id, PrincipalRow.display_name).where(
                    PrincipalRow.id.in_(wanted)
                )
            )
            return {str(one_id): str(name) for one_id, name in found.all()}


def people_names_of(request: Request) -> PeopleNames | None:
    """`app.state.people_names` when something put one there, the database otherwise, or None.

    None on a process built without a database, where an answer then names nobody and the screen
    draws what the rows say: a name is a courtesy, and its absence must not fail a read.
    """
    found = getattr(request.app.state, "people_names", None)
    if isinstance(found, PeopleNames):
        return found
    factory = sessions_of(request)
    return None if factory is None else StoredPeopleNames(factory)


async def names_for(request: Request, principal_ids: Collection[str]) -> dict[str, str]:
    """The names of exactly these ids, or none on a process that has nowhere to read them."""
    wanted = {one for one in principal_ids if one}
    source = people_names_of(request)
    if source is None or not wanted:
        return {}
    found = await source.names(wanted)
    # Held to the ids asked about, whatever a store returned, so an answer never names a stranger.
    return {one: name for one, name in found.items() if one in wanted}
