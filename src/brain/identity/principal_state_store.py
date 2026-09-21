"""Disabling somebody and enabling them again: one column on `auth.principal`, and its cascade.

`0003` built the cascade M1.2.3 asks for, a trigger that ends every live session of a principal the
moment `disabled_at` is set and moves their grants version, and until 2026-09-21 nothing any route
could reach ever set or cleared the column. `brain.identity.lifecycle.disable` and
`brain.console.global_surfaces.disable_principal` decide a leaver's disable over objects in memory
and nothing imports the second. This is the SQL for the reversible one, and it decides nothing:
who may do it is `brain.console.global_surfaces.may_disable`, handed in as a callable because it has
to be asked about the row under its lock.

**Disabling keeps the grants and makes them inert; enabling gives them back and no session.** The
resolver (`gate.held_grants`, `0048`) counts no grant of a disabled principal, the bearer refuses
their token (`brain.identity.principal_store.principal_from`) and the trigger ends their sessions,
so a disable takes everything away at once without deleting anything. Clearing the column restores
the grants and the ability to sign in, and never the sessions that were ended, which is `0003`'s
design: a session is evidence about the moment it opened. A leaver whose grants should go is the
access review's removal or `lifecycle.disable`, not this. See
`A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT`.

**The act is recorded, both ways, and attributed in its own transaction.** `0095b`'s trigger
appends one `principal_state` entry for a disable and one for an enable, so restoring access is on
the record as surely as taking it away. `brain.actor_id`, `brain.ent_hash` and `brain.trace_id` are
set before the update, so that entry, and the `session_end` entries `0050` appends for the sessions
the cascade ends, name the administrator rather than `unattributed`.

**Only a change is written.** Disabling somebody already disabled, or enabling somebody enabled,
writes nothing and says so, so two administrators pressing at once record one act.

Task ids: M1.2.3
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.identity import PrincipalRow

#: Why this disable is a column and not a deletion.
A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT: Final = (
    "Disabling somebody stops their sign-in, ends every session they have and makes every grant "
    "they hold inert, and deletes nothing, so enabling them again gives the grants back. It does "
    "not give back a session: they sign in again. Somebody who has left should have their grants "
    "removed as well."
)


class StateChange(enum.StrEnum):
    """What a press of the control did."""

    CHANGED = "changed"
    #: Already in the state asked for. Nothing written.
    ALREADY = "already"


@dataclass(frozen=True)
class PrincipalState:
    """One principal's disabled state after the act, and the database's instant for it."""

    principal_id: str
    department: str | None
    disabled_at: datetime | None
    outcome: StateChange
    #: The database's instant for the change, or None when nothing changed.
    at: datetime | None = None


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class StoredPrincipalStates:
    """`auth.principal.disabled_at` over this install's database, as the application role."""

    sessions: async_sessionmaker[AsyncSession]

    async def set_disabled(
        self,
        principal_id: str,
        *,
        disabled: bool,
        may: Callable[[str | None], bool],
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> PrincipalState | None:
        """Disable or enable one live principal the decision admits, or None.

        `may` is asked with the principal's department under the row's lock; a principal who is
        retired, absent or not admitted is None, one answer for all three.
        """
        async with self.sessions() as session, session.begin():
            row = (
                await session.execute(
                    select(PrincipalRow.primary_department, PrincipalRow.disabled_at)
                    .where(PrincipalRow.id == principal_id, PrincipalRow.deleted_at.is_(None))
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                return None
            department, was = row
            if not may(department):
                return None
            if (was is not None) == disabled:
                return PrincipalState(principal_id, department, was, StateChange.ALREADY)
            await session.execute(_set_config(ACTOR_SETTING, by))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            written = await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == principal_id)
                .values(disabled_at=func.statement_timestamp() if disabled else None)
                .returning(PrincipalRow.disabled_at, func.statement_timestamp())
            )
            disabled_at, at = written.one()
        return PrincipalState(principal_id, department, disabled_at, StateChange.CHANGED, at)
