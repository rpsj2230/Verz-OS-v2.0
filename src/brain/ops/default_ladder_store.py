"""Writing the default ladder into `ops.routing_rung`, from the wizard and at a start.

`brain.models.default_ladder` decides what the defaults are and when they may be written; this is
the half that owns a session, for the layout's rule that nothing deciding policy owns a client.

**The same table and the same trigger as the Routing screen.** The rows go into `ops.routing_rung`
as the application role, under the table's own policy, and `0059`'s `routing_rung_is_audited`
appends one `routing` entry per row, `added`, to the chain every other rung change is on. The
actor is set for the transaction through `brain.tables.audit.attributed_to`, the statements
`brain.routing_routes` runs before a save, so the entry names who wrote the ladder rather than
the database role marked inferred. It is `brain.firstrun.GRANTED_BY` from the wizard and at a
start alike: the defaults are what first run writes, and a start writing them is first run's
write arriving late, which is how `brain.identity.administration_reconciliation` attributes its
own grants.

**Idempotent by a lock and two reads, in one transaction.** `pg_advisory_xact_lock` on a number of
this module's own serialises two processes starting together, so the second finds the first's
rows live and writes nothing. Under the lock the write goes ahead only when no rung is live and
the ledger holds no `routing` entry at all, which is
`default_ladder.A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT`: the table's policy hides a
retired rung, so the ledger is the only record that a ladder was ever held. The partial unique
index on a tier's live positions is the backstop if the lock is ever taken out, and it refuses
rather than duplicates. A transaction-scoped lock rather than a session one, because PgBouncer
hands a connection to somebody else between transactions.

**At a start, `brain.models.default_ladder.reconcile` decides and this writes.**
`brain.app.lifespan` counts the administrators through `FirstAdministrators.administrators`, the
count the wizard's own door is judged by, after the installation settings and the vault's keys
are loaded, because the profile and the held keys are what name the provider, and a failure
never stops the process.

**Nothing here logs at all.** The callers log the provider's slug and the outcome, which are names.

Task ids: M27.8.8, M5.3.1
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from sqlalchemy import Insert, Select, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import AuditAction
from brain.core.scope import Scope
from brain.models.default_ladder import DefaultRung, LadderWritten, default_ladder
from brain.tables.audit import AuditEntryRow, attributed_to
from brain.tables.routing import RoutingRungRow

#: The advisory lock the default ladder is written under. Its own number, beside first run's, the
#: unlink's, the migration's and the ledger's, which a test holds it apart from.
DEFAULT_LADDER_LOCK: Final = 8274419103

#: A rung's scope when nothing narrows it: `Scope.model_dump()` of the unrestricted scope, which
#: is the shape `brain.tables.gate.SCOPE_SHAPE` checks.
UNRESTRICTED_SCOPE: Final[dict[str, Any]] = Scope().model_dump()


def any_live_rung() -> Select[tuple[Any]]:
    """One live rung's id, or none. `deleted_at` tested here as well as by the policy."""
    return select(RoutingRungRow.id).where(RoutingRungRow.deleted_at.is_(None)).limit(1)


def any_routing_entry() -> Select[tuple[int]]:
    """One `routing` ledger entry's position, or none: whether a rung was ever recorded."""
    return (
        select(AuditEntryRow.seq).where(AuditEntryRow.action == AuditAction.ROUTING.value).limit(1)
    )


def insert_rungs(rungs: Iterable[DefaultRung]) -> Insert:
    """One statement for every default row, so the rows and their entries commit together."""
    return insert(RoutingRungRow).values(
        [
            {
                "tier": one.tier.value,
                "scope": UNRESTRICTED_SCOPE,
                "position": one.position,
                "role": one.role.value,
                "deployment_id": one.deployment_id,
                "provider": one.provider,
                "model": one.model,
                "attempts": one.attempts,
                "timeout_seconds": one.timeout_seconds,
                "max_concurrency": one.max_concurrency,
                "enabled": True,
            }
            for one in rungs
        ]
    )


class SessionLadderWriter:
    """`brain.models.default_ladder.LadderWriter` over the application's sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def write(self, provider: str, *, actor: str, trace_id: str) -> LadderWritten:
        """Write the provider's defaults into a ladder nobody has held, or say why not.

        Raises for a database that refuses, and for a provider with no defaults; the callers
        decide what that costs, and neither lets it stop what they were doing.
        """
        rungs = default_ladder(provider)
        async with self.sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor, ent_hash="", trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": DEFAULT_LADDER_LOCK}
            )
            if (await session.execute(any_live_rung())).first() is not None:
                return LadderWritten.HELD
            if (await session.execute(any_routing_entry())).first() is not None:
                return LadderWritten.EMPTIED
            await session.execute(insert_rungs(rungs))
        return LadderWritten.WRITTEN
