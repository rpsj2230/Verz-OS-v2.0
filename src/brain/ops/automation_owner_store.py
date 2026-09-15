"""Where an automation's registration is kept, over `gate.automation_owner` from `0044`.

It holds the SQL and decides nothing, which is the split `brain.ops.limits` and
`brain.ops.limit_store` make: who an automation runs as and whether it may run is
`brain.ops.automation_owner`, and the order a call's checks run in is `brain.automation_routes`.

**Every read names the automation or the person first, so row-level security has something to
narrow on.** `registration` tells the transaction which automation is calling before it selects,
and the policy admits that row alone. See `THE_DATABASE_IS_TOLD_WHICH_AUTOMATION_IS_CALLING`.

**A row is rebuilt through `Registration` and `Grant` on every read, and refused rather than
repaired.** A ceiling edited into something `Grant` will not construct, or a registration that
fails its own checks, is logged and absent. An automation that cannot be read is an automation
that cannot call, which is the safe direction and the one `brain.gate.suspension_store` takes
about a row that disagrees with its digest.

**An adoption is decided under a row lock and written once.** `adopt` reads the row `FOR UPDATE`
and asks the owner's standing while it is held. Two people adopting one automation at once
therefore write one owner: the second waits for the first, then finds an automation whose owner
is live and is refused.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import EntitlementSet, Grant
from brain.core.principal import Principal
from brain.ops.automation_owner import PrincipalRecords, Registration, adopt
from brain.tables.automation import AutomationOwnerRow

log = structlog.get_logger()

#: Why the transaction is told which automation it is reading for.
THE_DATABASE_IS_TOLD_WHICH_AUTOMATION_IS_CALLING: Final = (
    "A call names one automation, and the transaction is told which before anything is read, "
    "so the policy hands over that row and no other. A lookup that forgot its WHERE clause "
    "would otherwise return every automation's ceiling to a caller holding one credential."
)

AUTOMATION_SETTING: Final = "app.automation_id"
PRINCIPAL_SETTING: Final = "app.principal_id"


class AutomationStoreError(Exception):
    """A registration could not be written, read or adopted as asked."""


def row_values(registration: Registration) -> dict[str, Any]:
    """What `put` writes. The ceiling as grant dumps, the tools sorted.

    Grants only, and nothing is lost by it: `Registration` refuses a ceiling with an expiry,
    so there is no time bound to drop.
    """
    return {
        "automation_id": registration.automation_id,
        "owner_principal_id": registration.owner_principal_id,
        "credential_digest": registration.credential_digest,
        "declared_tools": sorted(registration.declared_tools),
        "ceiling": [grant.model_dump(mode="json") for grant in registration.ceiling.grants],
    }


def registration_from(row: Mapping[str, Any]) -> Registration:
    """A row's columns as a registration. Raises when the row does not construct."""
    try:
        grants = tuple(Grant.model_validate(one) for one in row["ceiling"])
        return Registration(
            automation_id=row["automation_id"],
            owner_principal_id=row["owner_principal_id"],
            credential_digest=row["credential_digest"],
            declared_tools=frozenset(row["declared_tools"]),
            ceiling=EntitlementSet(principal_id=row["automation_id"], grants=grants),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        msg = (
            f"automation {row.get('automation_id')!r} holds a registration that does not construct"
        )
        raise AutomationStoreError(msg) from exc


def _readable(row: Mapping[str, Any]) -> Registration | None:
    """A row as a registration, or None and a log line. See the module note on refused rows."""
    try:
        return registration_from(row)
    except AutomationStoreError as exc:
        log.warning(
            "automation.registration_refused", automation=row.get("automation_id"), error=str(exc)
        )
        return None


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class StoredAutomations:
    """`gate.automation_owner`. Implements `brain.automation_routes.RegistrationSource`."""

    sessions: async_sessionmaker[AsyncSession]

    async def registration(self, automation_id: str) -> Registration | None:
        """The registration for this automation, read as that automation, or None."""
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(AUTOMATION_SETTING, automation_id))
            row = (
                (
                    await session.execute(
                        select(AutomationOwnerRow.__table__).where(
                            AutomationOwnerRow.automation_id == automation_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _readable(dict(row))

    async def put(self, registration: Registration) -> None:
        """Register an automation in its owner's name. A second write for one id raises."""
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, registration.owner_principal_id))
            await session.execute(insert(AutomationOwnerRow).values(**row_values(registration)))

    async def adopt(
        self,
        automation_id: str,
        *,
        new_owner: Principal,
        principals: PrincipalRecords,
        now: datetime,
    ) -> Registration | None:
        """Hand an automation awaiting an owner to this person, under a lock. None when absent.

        `brain.ops.automation_owner.adopt` decides; this reads the row, asks the registered
        owner's standing while the row is held, and writes the one column. Raises
        `RegistrationError` when the automation still has a live owner or the new owner is not
        live, and writes nothing then.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(AUTOMATION_SETTING, automation_id))
            await session.execute(_set_config(PRINCIPAL_SETTING, new_owner.id))
            row = (
                (
                    await session.execute(
                        select(AutomationOwnerRow.__table__)
                        .where(AutomationOwnerRow.automation_id == automation_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            found = registration_from(dict(row))
            adopted = adopt(
                found,
                current_owner=await principals.live_principal(found.owner_principal_id),
                new_owner=new_owner,
                now=now,
            )
            # By id alone, and with no check on how many rows changed. The row is held `FOR
            # UPDATE` from the read above to the end of this transaction, so the owner the
            # decision was taken about is the owner being replaced; a second clause naming it, or
            # a rowcount check, would guard a change nothing can make, and a guard nothing can
            # reach is the recurring defect `brain.ops.guards` exists to find. The policy in
            # `0044` is what refuses a new owner other than the session's own.
            await session.execute(
                update(AutomationOwnerRow)
                .where(AutomationOwnerRow.automation_id == automation_id)
                .values(owner_principal_id=adopted.owner_principal_id)
            )
        return adopted
