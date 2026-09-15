"""Who exists here now, read from `auth.principal` on the application's own pool.

`brain.ops.automation_owner.PrincipalRecords` is how an automation's call learns whether its
owner is still here, and nothing implemented it, so `app.state.automation` could not be built.
This is that implementation. It holds the SQL and decides nothing: whether the automation runs
is `brain.ops.automation_owner.standing_of`.

**Disabled and deleted are absent; ended is not.** A disabled or deleted principal is `None`, for
the reason the protocol gives: a real `Principal` on a code path is one somebody computes a reach
for. A principal whose `not_after` has passed is returned as it is, and the caller judges it with
the instant it is asking at. Filtering on the date here would judge it at the database's clock,
which is not the call's, and would make an ended engagement indistinguishable from a deletion to
the one reader who needs to tell them apart, the adoption screen. See
`AN_ENDED_ENGAGEMENT_IS_THE_CALLERS_TO_JUDGE`.

**Both absences are decided here and again by the database, and the two are not the same
check.** The policy on `auth.principal` in `0002` hides a deleted row from the application role
and says nothing about a disabled one, and a connection that is not the application role bypasses
it entirely. So `principal_from` reads both columns and refuses both, and does not rely on the
role the store happened to be handed.

**A row that does not construct is absent, and logged.** It came from somewhere other than
`Principal`, whose validators the table's check constraints only mirror. An owner who cannot be
read is an owner whose automation stops, which is the safe direction and the one
`brain.ops.automation_owner_store` takes about a registration.

**The transaction is told whose record it is reading**, for the reason
`brain.gate.entitlement_store` gives about grants: nothing reads it today, and a policy that
narrows a principal read to the principal named lands without a store change.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.principal import Principal
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()

#: Why the date is left on the record.
AN_ENDED_ENGAGEMENT_IS_THE_CALLERS_TO_JUDGE: Final = (
    "A principal whose not_after has passed is returned with it. Whether that date has passed "
    "is asked with the instant the caller is working at, by Principal.is_active, and a store "
    "that dropped the row at its own clock would decide it at a moment nobody asked about."
)

PRINCIPAL_SETTING: Final = "app.principal_id"

#: The columns `principal_from` reads. `disabled_at` and `deleted_at` are read to be refused.
COLUMNS: Final = (
    PrincipalRow.id,
    PrincipalRow.kind,
    PrincipalRow.employment,
    PrincipalRow.display_name,
    PrincipalRow.primary_department,
    PrincipalRow.not_after,
    PrincipalRow.disabled_at,
    PrincipalRow.deleted_at,
)


class PrincipalStoreError(Exception):
    """A principal's row does not construct as a `Principal`."""


def principal_from(row: Mapping[str, Any]) -> Principal | None:
    """A row as the live principal it records, None when disabled or deleted, or a raise."""
    if row["deleted_at"] is not None or row["disabled_at"] is not None:
        return None
    try:
        return Principal(
            id=row["id"],
            kind=row["kind"],
            employment=row["employment"],
            display_name=row["display_name"],
            primary_department=row["primary_department"],
            not_after=row["not_after"],
        )
    except ValidationError as exc:
        msg = f"principal {row.get('id')!r} holds a record that does not construct"
        raise PrincipalStoreError(msg) from exc


def _readable(row: Mapping[str, Any]) -> Principal | None:
    """A row as a live principal, or None and a log line. See the module note on refused rows."""
    try:
        return principal_from(row)
    except PrincipalStoreError as exc:
        log.warning("principal.record_refused", principal=row.get("id"), error=str(exc))
        return None


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class StoredPrincipals:
    """`auth.principal`. Implements `brain.ops.automation_owner.PrincipalRecords`."""

    sessions: async_sessionmaker[AsyncSession]

    async def live_principal(self, principal_id: str) -> Principal | None:
        """The principal with this id if they are here and not disabled, or None."""
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            row = (
                (await session.execute(select(*COLUMNS).where(PrincipalRow.id == principal_id)))
                .mappings()
                .one_or_none()
            )
        return None if row is None else _readable(dict(row))
