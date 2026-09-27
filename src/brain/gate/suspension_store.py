"""Where a suspended action is kept between the request that raised it and the one that decides it.

`brain.approval_routes` reads suspensions through `SuspensionSource` and nothing implemented it,
so the queue had no store in any process and a decision had nowhere to be written. This is that
store, over `gate.suspension` from `0042`. It holds the SQL and decides nothing: who may see a
suspension is `brain.console.approvals.card`, what a decision does is
`brain.console.approvals.decide`, and the order the two run in is `brain.approval_routes`.

**Every read is made at a reach, so row-level security has something to narrow on.** The policy
admits a pending row whose capability is in `app.approvable`, and `approvable` is the reach's own
answer: the distinct capabilities pending suspensions require are read from the view, and
`EntitlementSet.holds` says which of them this reader holds at this instant. Nothing here
restates `Capability.covers` or an expiry. See `THE_DATABASE_IS_TOLD_WHAT_THE_REACH_HOLDS_AND_
NEVER_WORKS_IT_OUT`.

**A row is re-checked against its own digest on every read, and refused rather than repaired.**
`stored_from` rebuilds the action from JSON and compares its digest and its capability with the
columns beside it. The application role cannot edit those columns, so a mismatch is somebody with
more than that role, and an approver pressing approve on it would approve something other than
what was raised. A refused row is logged and absent, for the reason `brain.approval_routes` gives
about a suspension that does not make a card: one bad row must not take the queue down.

**A decision is taken under a row lock and written once.** `holding` opens one transaction, and
`HeldRows.lock` reads the row `FOR UPDATE`, so a second request deciding the same suspension
waits for the first and then finds it decided. `HeldRows.record` updates only a pending row at
the digest that was decided and reports whether one row changed; the update policy in `0042`
refuses a decided row as well, so the clause is what makes a refusal loud rather than a quiet
nothing, which is the argument `brain.browsing.envelope_store.record_decision` makes.

**The ledger entry is written by the row, in the statement that decides it.** Until `0083` this
store was built with a ledger writer and `decide` wrote the entry through it before the row moved,
which left one ordering open: an entry recording a decision whose row write then failed. No writer
for `obs.audit_entry` existed in the process, so no process built this store and every decision on
a running install was refused. Now the row carries the verdict and the reason code, `0083`'s
trigger appends the `approval` entry when the row stops being pending, and the decision and its
entry commit or roll back together. See `THE_RECORDER_DRAFTS_THE_ENTRY_AND_THE_ROW_KEEPS_IT`.

**`brain.console.approvals.decide` still decides, and its recorder still builds the entry.**
`AuditRecorder.approval` holds the rules about a reason code and the shape of the details, and a
second statement of them here would drift. So the route hands `decide` a recorder over a chain of
its own, which drafts the entry and keeps nothing, and `record` writes the draft's verdict and
reason onto the row, tells the trigger the decider's reach digest and the request's trace, and
reads back the entry the database kept. A kept entry that says something other than the draft is
refused inside the transaction, so a trigger and a recorder that have drifted apart stop a
decision rather than record a different one.

Rejected: a `LedgerWriter` whose `append` stages the entry for the trigger. `append` is synchronous
and returns an `AuditEntry` with its sequence and both digests, which do not exist until the row's
UPDATE has run, so every value it could return would be a forged link, the thing
`brain.audit.ledger.AuditChain.append` refuses to let a caller choose. A writer held by the store
would also be shared by every request deciding at once.

Rejected: appending to `obs.audit_entry` from here, which `brain_app` is granted. Every persisted
entry is written by a trigger on a row, for the reason `0054` gives, so a decision an operator
writes at a prompt is recorded exactly as one pressed in the console and the chain has one writer.

**A resume re-resolves the reach and hands the stored row to `brain.gate.leash.resume`.**
`resume_stored` takes the function that resolves a principal's reach now, not the reach the
approval was granted at, so everything `resume` re-checks is checked against the present. What
it reads is `state`, which the decision wrote and a check holds the verdict to.

Task ids: M35.3.1.1, M33.6.1.3, M27.9.3
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

import structlog
from pydantic import ValidationError
from sqlalchemy import CursorResult, column, insert, select, table, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import AuditAction, AuditEntry
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import Entity, TypedResult
from brain.core.field_policy import FieldPolicy
from brain.gate.injection import RiskAssessment
from brain.gate.leash import Action, ApprovalState, Leash, Resumption, SuspendedAction, resume
from brain.ops.idempotency import OperationLedger
from brain.tables.audit import AuditEntryRow, attributed_to
from brain.tables.suspension import SuspensionRow

log = structlog.get_logger()

#: Why the policy reads a list of capabilities rather than evaluating a grant.
THE_DATABASE_IS_TOLD_WHAT_THE_REACH_HOLDS_AND_NEVER_WORKS_IT_OUT: Final = (
    "Capability.covers expands a trailing wildcard and an expired principal holds nothing. A "
    "policy that matched grants itself would be a second implementation of both, and the "
    "wrong copy is the one in production. So the store asks the reach which of the pending "
    "capabilities it holds and tells the database the answer, and the policy compares strings."
)

#: Why a row that disagrees with its digest is absent rather than shown.
A_ROW_THAT_DISAGREES_WITH_ITS_DIGEST_IS_NOT_WHAT_WAS_RAISED: Final = (
    "The digest is what the artefact was rendered for and what an approval binds to. A row "
    "whose action no longer produces it describes something other than what was raised, and "
    "approving it would approve the edit. It is refused on read, logged, and absent."
)

#: Why a decision's entry is drafted in the process and kept by the database.
THE_RECORDER_DRAFTS_THE_ENTRY_AND_THE_ROW_KEEPS_IT: Final = (
    "AuditRecorder.approval holds the rules about what an approval entry says, and a trigger on "
    "gate.suspension is the only thing that writes one, in the transaction that decides the row. "
    "So the recorder drafts the entry on a chain nobody keeps, the row is written with the draft's "
    "verdict and reason, and the entry the trigger kept is read back and must say what the draft "
    "said. A decision whose kept entry says anything else is not taken."
)

PRINCIPAL_SETTING: Final = "app.principal_id"
APPROVABLE_SETTING: Final = "app.approvable"

#: The view `0042` builds. Declared here as a lightweight table: it is not a model, because it
#: holds nothing and autogenerate must not propose creating it as a table.
PENDING_CAPABILITIES: Final = table(
    "suspension_capability", column("required_capability"), schema="gate"
)


class SuspensionStoreError(Exception):
    """A suspension could not be written, read or decided as asked."""


# ------------------------------------------------------------------------ the row


def row_values(suspension: SuspendedAction) -> dict[str, Any]:
    """What `put_suspension` writes. Refuses a suspension that has already been decided.

    A suspension is stored when it is raised. One stored already decided would be a decision
    nobody took through `decide`, with no ledger entry behind it.
    """
    if suspension.state is not ApprovalState.PENDING or suspension.decided_at is not None:
        msg = (
            f"suspension {suspension.id!r} was decided before it was stored, so the decision "
            "has no ledger entry behind it"
        )
        raise SuspensionStoreError(msg)
    return {
        "id": suspension.id,
        "trace_id": suspension.trace_id,
        "principal_id": suspension.principal_id,
        "agent_id": suspension.action.agent_id,
        "required_capability": suspension.action.tool.required_capability,
        "action": suspension.action.model_dump(mode="json"),
        "ent_hash": suspension.ent_hash,
        "artefact": suspension.artefact,
        "action_digest": suspension.action_digest,
        "raised_at": suspension.raised_at,
        "expires_at": suspension.expires_at,
        "state": suspension.state.value,
    }


def stored_from(row: Mapping[str, Any]) -> SuspendedAction:
    """A row's columns as a suspension. Raises when the row disagrees with itself.

    See `A_ROW_THAT_DISAGREES_WITH_ITS_DIGEST_IS_NOT_WHAT_WAS_RAISED`.
    """
    try:
        action = Action.model_validate(row["action"])
    except ValidationError as exc:
        msg = f"suspension {row['id']!r} holds an action that does not construct"
        raise SuspensionStoreError(msg) from exc
    if action.digest() != row["action_digest"]:
        msg = (
            f"suspension {row['id']!r} no longer matches its digest. "
            f"{A_ROW_THAT_DISAGREES_WITH_ITS_DIGEST_IS_NOT_WHAT_WAS_RAISED}"
        )
        raise SuspensionStoreError(msg)
    if action.tool.required_capability != row["required_capability"]:
        msg = (
            f"suspension {row['id']!r} is filed under a capability its action does not require, "
            "so the policy narrowed on something other than the action"
        )
        raise SuspensionStoreError(msg)
    try:
        return SuspendedAction(
            id=row["id"],
            trace_id=row["trace_id"],
            action=action,
            principal_id=row["principal_id"],
            ent_hash=row["ent_hash"],
            artefact=row["artefact"],
            action_digest=row["action_digest"],
            raised_at=row["raised_at"],
            expires_at=row["expires_at"],
            state=ApprovalState(row["state"]),
            decided_by=row["decided_by"] or "",
            decided_at=row["decided_at"],
        )
    except (ValidationError, ValueError) as exc:
        msg = f"suspension {row['id']!r} does not construct"
        raise SuspensionStoreError(msg) from exc


def _readable(row: Mapping[str, Any]) -> SuspendedAction | None:
    """A row as a suspension, or None and a log line. See the module note on refused rows."""
    try:
        return stored_from(row)
    except SuspensionStoreError as exc:
        log.warning("stored suspension refused", suspension=row.get("id"), error=str(exc))
        return None


def approvable(pending: Sequence[str], reach: EntitlementSet, now: datetime) -> tuple[str, ...]:
    """Which of these pending capabilities this reach holds at this instant, sorted.

    A name that is not a capability is dropped rather than raised: it came out of a table, the
    reader cannot hold it, and refusing the whole read over it would hide every approval beside
    it. Asked through `EntitlementSet.holds` and nothing else.
    """
    held: set[str] = set()
    for name in pending:
        try:
            capability = Capability(value=name)
        except ValidationError:
            continue
        if reach.holds(capability, now):
            held.add(name)
    return tuple(sorted(held))


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def at_reach(session: AsyncSession, reach: EntitlementSet, now: datetime) -> None:
    """Tell this transaction who is reading and which pending capabilities they hold.

    `set_config(..., true)`, so both last for the transaction and no longer, which is the trap
    `brain.knowledge.search._set_config` records about a pooled connection.
    """
    pending = (await session.execute(select(PENDING_CAPABILITIES.c.required_capability))).scalars()
    await session.execute(_set_config(PRINCIPAL_SETTING, reach.principal_id))
    await session.execute(
        _set_config(APPROVABLE_SETTING, ",".join(approvable(list(pending), reach, now)))
    )


async def put_suspension(session: AsyncSession, suspension: SuspendedAction) -> None:
    """Write a raised suspension once. Does not commit. A second write for one id raises.

    The session must already be `at_reach` for the principal the suspension runs as: `0042`
    admits an insert in that principal's name only.
    """
    await session.execute(insert(SuspensionRow).values(**row_values(suspension)))


# --------------------------------------------------------------------- the reading side


@dataclass(frozen=True)
class ReachedSuspensions:
    """The store as one reach sees it. Implements `brain.approval_routes.SuspensionSource`."""

    sessions: async_sessionmaker[AsyncSession]
    reach: EntitlementSet
    now: datetime

    async def open_suspensions(self) -> Sequence[SuspendedAction]:
        """Every pending suspension the policy admits for this reach. `card` decides the rest."""
        async with self.sessions() as session, session.begin():
            await at_reach(session, self.reach, self.now)
            rows = await session.execute(
                select(SuspensionRow.__table__).where(
                    SuspensionRow.state == ApprovalState.PENDING.value
                )
            )
            found = [_readable(dict(row)) for row in rows.mappings()]
        return [one for one in found if one is not None]

    async def suspension(self, suspension_id: str) -> SuspendedAction | None:
        """One suspension the policy admits for this reach, whatever its state, or None."""
        async with self.sessions() as session, session.begin():
            await at_reach(session, self.reach, self.now)
            row = (
                (
                    await session.execute(
                        select(SuspensionRow.__table__).where(SuspensionRow.id == suspension_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _readable(dict(row))


# -------------------------------------------------------------------- the deciding side


@dataclass(frozen=True)
class HeldRows:
    """One transaction's hold on the table. Implements `brain.approval_routes.HeldSuspensions`."""

    session: AsyncSession

    async def lock(self, suspension_id: str) -> SuspendedAction | None:
        """The row, locked until the transaction ends, or None when the policy admits none."""
        row = (
            (
                await self.session.execute(
                    select(SuspensionRow.__table__)
                    .where(SuspensionRow.id == suspension_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _readable(dict(row))

    async def record(self, decided: SuspendedAction, entry: AuditEntry) -> AuditEntry | None:
        """Write a decision over its pending row at its digest, and return the entry kept for it.

        `entry` is the draft `brain.console.approvals.decide` built, and the row takes its verdict
        and reason code. None when no pending row at that digest changed, which writes nothing.
        Raises when the kept entry is missing or says anything the draft does not, including an
        entry about another suspension or by another person, which rolls the decision back. See
        `THE_RECORDER_DRAFTS_THE_ENTRY_AND_THE_ROW_KEEPS_IT`.
        """
        if decided.state is ApprovalState.PENDING or decided.decided_at is None:
            msg = f"suspension {decided.id!r} has not been decided, so there is nothing to record"
            raise SuspensionStoreError(msg)
        for statement in attributed_to(
            actor_id=entry.actor_id, ent_hash=entry.ent_hash, trace_id=entry.trace_id
        ):
            await self.session.execute(statement)
        # `CursorResult` rather than `Result`, which is what an UPDATE returns and is the only
        # one carrying `rowcount`. Cast at a library boundary where proving the match buys nothing.
        changed = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(SuspensionRow)
                .where(
                    SuspensionRow.id == decided.id,
                    SuspensionRow.state == ApprovalState.PENDING.value,
                    SuspensionRow.action_digest == decided.action_digest,
                )
                .values(
                    state=decided.state.value,
                    decided_by=decided.decided_by,
                    decided_at=decided.decided_at,
                    verdict=entry.details.get("verdict"),
                    reason_code=entry.details.get("reason_code"),
                )
            ),
        )
        if changed.rowcount != 1:
            return None
        kept = await self._kept(entry.subject)
        if kept is None or recorded_differently(kept, entry):
            msg = (
                f"suspension {decided.id!r} was decided and the ledger does not hold the entry "
                f"its recorder drafted. {THE_RECORDER_DRAFTS_THE_ENTRY_AND_THE_ROW_KEEPS_IT}"
            )
            raise SuspensionStoreError(msg)
        return kept

    async def _kept(self, subject: str) -> AuditEntry | None:
        """The newest approval entry about this subject, which the trigger has just appended.

        Newest, because the trigger took the ledger's advisory lock and this transaction still
        holds it, so nothing has been appended after it.
        """
        row = (
            (
                await self.session.execute(
                    select(AuditEntryRow.__table__)
                    .where(
                        AuditEntryRow.subject == subject,
                        AuditEntryRow.action == AuditAction.APPROVAL.value,
                    )
                    .order_by(AuditEntryRow.seq.desc())
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else AuditEntry.model_validate(dict(row))


def recorded_differently(kept: AuditEntry, drafted: AuditEntry) -> bool:
    """Whether the kept entry says something other than the draft.

    Every field but the four the ledger assigns: the sequence, the instant and the two digests.
    """
    return (
        kept.actor_id,
        kept.action,
        kept.subject,
        kept.ent_hash,
        kept.trace_id,
        kept.details,
    ) != (
        drafted.actor_id,
        drafted.action,
        drafted.subject,
        drafted.ent_hash,
        drafted.trace_id,
        drafted.details,
    )


@dataclass(frozen=True)
class StoredSuspensions:
    """`gate.suspension`, read at a reach and decided on a held row.

    Implements `brain.approval_routes.SuspensionStore`, and is what `app.state.suspensions` holds
    on a process with a database. Until 2026-09-17 it was built with a ledger writer, and no
    process had one; see the module docstring.
    """

    sessions: async_sessionmaker[AsyncSession]

    def reading_as(self, reach: EntitlementSet, now: datetime) -> ReachedSuspensions:
        return ReachedSuspensions(self.sessions, reach, now)

    @asynccontextmanager
    async def holding(self, reach: EntitlementSet, now: datetime) -> AsyncIterator[HeldRows]:
        """One transaction at this reach, committed when the block ends, rolled back on a raise."""
        async with self.sessions() as session, session.begin():
            await at_reach(session, reach, now)
            yield HeldRows(session)


# ------------------------------------------------------------------------- resuming


async def resume_stored[T: Entity](
    store: StoredSuspensions,
    suspension_id: str,
    principal_id: str,
    *,
    reach_now: Callable[[str], EntitlementSet],
    agent_ceiling: EntitlementSet,
    policy: FieldPolicy,
    leash: Leash,
    assessment: RiskAssessment,
    trace_id: str,
    now: datetime,
    execute: Callable[[Action], TypedResult[T]],
    ledger: OperationLedger,
) -> Resumption[T] | None:
    """Resume a stored suspension through `brain.gate.leash.resume`, at the reach as it is now.

    `reach_now` resolves the principal's reach at the moment of the resume, which is the point:
    an approval granted on Monday must not execute on Friday under the grants Monday had, and
    `resume` can only notice a change if the reach it is handed is Friday's. The suspension is
    read at that same reach, so the policy's own-row clause is what admits it. None when nothing
    is stored for this principal under that id.

    `ledger` is the operation ledger the run is keyed in, so a resume retried after the action
    ran is handed what the first run left rather than running it again. See
    `brain.gate.leash.AN_ACTION_THAT_ALREADY_RAN_IS_REPORTED_AND_NOT_RUN_AGAIN`.
    """
    reach = reach_now(principal_id)
    found = await store.reading_as(reach, now).suspension(suspension_id)
    if found is None:
        return None
    return resume(
        found,
        caller=reach,
        agent_ceiling=agent_ceiling,
        policy=policy,
        leash=leash,
        assessment=assessment,
        trace_id=trace_id,
        now=now,
        execute=execute,
        ledger=ledger,
    )
