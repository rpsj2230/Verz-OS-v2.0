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

**Idempotent by a lock and the reads under it, in one transaction.** `pg_advisory_xact_lock` on a
number of this module's own serialises two processes starting together, so the second finds the
first's rows live and writes nothing. Under the lock the write goes ahead only when no rung is live
and the ledger holds no `routing` entry at all, which is
`default_ladder.A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT`: the table's policy hides a
retired rung, so the ledger is the only record that a ladder was ever held. The partial unique
index on a tier's live positions is the backstop if the lock is ever taken out, and it refuses
rather than duplicates. A transaction-scoped lock rather than a session one, because PgBouncer
hands a connection to somebody else between transactions.

**A live ladder is completed only when it is the product's earlier default, untouched**
(`default_ladder.AN_UNTOUCHED_EARLIER_DEFAULT_IS_COMPLETED_ONCE`). Under the same lock the live rows
are read and handed to `default_ladder.completion`, which answers the missing steps only when the
rows are exactly `earlier_default`, and `ops.routing_change` is asked whether any change was ever
applied, because an edit that was later put back leaves the rows looking untouched and the change
table remembering. A held change is not asked about: it changed nothing. The missing rows go in
with one statement, in level and step order, so `0097`'s role trigger derives each against the
steps inserted before it, and `0059`'s trigger records each as `added` by the same actor. Once
completed, the live rows are no longer the earlier default and the next start adds nothing.

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
from brain.models.default_ladder import (
    DefaultRung,
    LadderWritten,
    WrittenStep,
    completion,
    default_ladder,
)
from brain.models.routing import Tier
from brain.tables.audit import AuditEntryRow, attributed_to
from brain.tables.model_registry import ChangeStatus, RoutingChangeRow
from brain.tables.routing import RoutingRungRow

#: The advisory lock the default ladder is written under. Its own number, beside first run's, the
#: unlink's, the migration's and the ledger's, which a test holds it apart from.
DEFAULT_LADDER_LOCK: Final = 8274419103

#: A rung's scope when nothing narrows it: `Scope.model_dump()` of the unrestricted scope, which
#: is the shape `brain.tables.gate.SCOPE_SHAPE` checks.
UNRESTRICTED_SCOPE: Final[dict[str, Any]] = Scope().model_dump()

#: The same scope as JSONB hands it back, a list where the model dump holds a tuple.
UNRESTRICTED_SCOPE_READ: Final[dict[str, Any]] = Scope().model_dump(mode="json")


def any_routing_entry() -> Select[tuple[int]]:
    """One `routing` ledger entry's position, or none: whether a rung was ever recorded."""
    return (
        select(AuditEntryRow.seq).where(AuditEntryRow.action == AuditAction.ROUTING.value).limit(1)
    )


def live_steps() -> Select[tuple[RoutingRungRow]]:
    """Every live rung, for the completion to compare with the earlier default. `deleted_at` is
    tested here as well as by the policy."""
    return select(RoutingRungRow).where(RoutingRungRow.deleted_at.is_(None))


def any_applied_change() -> Select[tuple[Any]]:
    """One applied routing change's id, or none: whether anybody ever changed the ladder."""
    return (
        select(RoutingChangeRow.id)
        .where(RoutingChangeRow.status == ChangeStatus.APPLIED.value)
        .limit(1)
    )


def as_written(row: RoutingRungRow) -> WrittenStep:
    """A live row as the completion compares it: every column the product writes but the role."""
    return WrittenStep(
        tier=Tier(row.tier),
        position=row.position,
        deployment_id=row.deployment_id,
        provider=row.provider,
        model=row.model,
        attempts=row.attempts,
        timeout_seconds=float(row.timeout_seconds),
        max_concurrency=row.max_concurrency,
        enabled=row.enabled,
        everywhere=row.scope == UNRESTRICTED_SCOPE_READ,
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
        """Write the provider's defaults into a ladder nobody has held, complete an untouched
        earlier default, or say why neither.

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
            live = [as_written(one) for one in (await session.execute(live_steps())).scalars()]
            if live:
                missing = completion(provider, live)
                if not missing:
                    return LadderWritten.HELD
                if (await session.execute(any_applied_change())).first() is not None:
                    return LadderWritten.HELD
                await session.execute(insert_rungs(missing))
                return LadderWritten.COMPLETED
            if (await session.execute(any_routing_entry())).first() is not None:
                return LadderWritten.EMPTIED
            await session.execute(insert_rungs(rungs))
        return LadderWritten.WRITTEN
