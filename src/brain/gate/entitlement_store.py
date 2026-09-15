"""Where a principal's reach is loaded from, over `gate.resolve_entitlements` from `0003`.

`brain.gate.resolve` has asked an `EntitlementStore` for a reach on every miss since it was
written, and nothing implemented one, so `app.state.gate` could not be built on any process.
This is that store. It holds one statement and decides nothing: whether a cached set may be
served is `resolve`, what a channel may use of it is `brain.gate.admission`, and whether a
principal may be told anything at all is every surface downstream.

**It calls the resolver in the database and writes no query over the grant tables.** `0003`
put the answer to "what does this person hold" in one SQL function so that the application and
the audit trigger ask the same question the same way, and `tests/unit/test_resolver.py` holds
that there is exactly one. A SELECT here joining `gate.capability_grant` and
`gate.capability_pack_assignment` would be a second resolver in Python's clothes, and it would be
the one that missed the next rule. See `ONE_RESOLVER_AND_THIS_IS_NOT_A_SECOND`.

Rejected: reading `auth.principal` and the grants in two statements and assembling the set here.
It is cheaper to write and it is exactly the drift `0003` exists to make impossible: the
function already refuses a disabled or deleted principal every grant, and a Python assembly
would have to remember to.

**Additive, and nothing here can subtract.** The function unions direct grants and pack
members; revocation is a retired row, which the policy hides and the function skips. There is no
parameter through which a caller could narrow or widen what comes back.

**The transaction is told whose grants it is reading before it reads.** The policies on the
grant tables in `0002` admit every live row to the application role today, so the setting
narrows nothing yet. It is set anyway, in the statement's own transaction, so a policy that
narrows a grant read to the principal it names lands without a store change and without a
window in which this store reads nothing. A test replaces the policy with one that reads it and
loads through the store. See `THE_DATABASE_IS_TOLD_WHOSE_GRANTS_ARE_READ`.

**A payload that does not construct raises, and is never an empty set.** `resolve` turns the
raise into `ResolutionFailedError`, which is the distinction its module docstring is built on.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import EntitlementSet

#: Why this store runs a function rather than a query.
ONE_RESOLVER_AND_THIS_IS_NOT_A_SECOND: Final = (
    "What a principal holds is answered by gate.resolve_entitlements and nowhere else. The "
    "audit trigger asks it on every grant write, so a resolver that has stopped working fails "
    "for the person making the change. A store assembling the set from the grant tables itself "
    "would be a second resolver, agreeing with the first until the day one of them changes."
)

#: Why the principal is named to the transaction.
THE_DATABASE_IS_TOLD_WHOSE_GRANTS_ARE_READ: Final = (
    "The transaction is told which principal's grants it is reading before the resolver runs, "
    "so a policy narrowing a grant read to that principal has something to narrow on. Set "
    "transaction-locally, because a session setting on a pooled connection is inherited by "
    "whoever borrows the connection next."
)

PRINCIPAL_SETTING: Final = "app.principal_id"

RESOLVE: Final = text("SELECT gate.resolve_entitlements(:principal_id, :at)")


class EntitlementStoreError(Exception):
    """The resolver's answer could not be read as a reach. Never an empty one."""


def entitlements_from(payload: object) -> EntitlementSet:
    """The resolver's JSON as the set it describes. Raises when it is not one.

    The principal id is taken from the payload and not checked against the one asked for:
    `resolve` makes that comparison for every store, and a second copy of it here would be a
    guard no store test could reach.
    """
    if not isinstance(payload, Mapping):
        msg = f"the resolver returned {type(payload).__name__}, which is not a reach"
        raise EntitlementStoreError(msg)
    try:
        return EntitlementSet.model_validate(dict(payload))
    except ValidationError as exc:
        msg = f"the resolver's answer for {payload.get('principal_id')!r} does not construct"
        raise EntitlementStoreError(msg) from exc


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class StoredEntitlements:
    """`gate.resolve_entitlements`. Implements `brain.gate.resolve.EntitlementStore`."""

    sessions: async_sessionmaker[AsyncSession]

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        """This principal's reach at this instant, from the one resolver.

        A principal who was never here, or who is disabled or deleted, holds nothing: that is
        the resolver's answer and a successful read, not a failure.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            payload = (
                await session.execute(RESOLVE, {"principal_id": principal_id, "at": now})
            ).scalar_one()
        return entitlements_from(payload)
