"""Where a sealed envelope and its approval are kept between the person and the container.

`brain.browsing.envelope` seals an envelope, `brain.browsing.approval` raises it for a person,
and `brain.browsing.enforcer.compile_policy` turns it into a policy with or without that
person's yes. Each of those happens at a different moment and usually in a different process,
and until this module the only thing carrying an approval from the first to the last was the
object in memory. This is the row between them (M19.2.3).

**Written once and never replaced.** `put_envelope` inserts and does not upsert. A run whose
envelope could be written again is a run whose permissions could be rewritten after a card was
approved, with the approval still pointing at the run id. A second write for one run is a
primary key violation, which is the loud outcome.

**A row is re-checked against its own digest on every read.** `StoredEnvelope` re-derives the
digest from the sealed parts through `brain.browsing.envelope.seal` and refuses a row where the
two differ. The application role cannot edit those columns, `0041` grants it UPDATE on the
decision alone, so a mismatch is somebody with more than that role, and the honest response is
to refuse to start anything on it.

**The decision is recorded against the digest that was approved, not only the run.**
`record_decision` updates a pending row for this run whose digest is the one the suspension
carries, and treats no row changed as a refusal. That is `0041`'s policy stated again in the
statement, for the reason `brain.ops.outbox_store` gives about its own guarded update: the
policy is what stops it, and the clause is what makes a refusal loud rather than a quiet nothing.

**One answer to whether a stored envelope is approved.** `StoredEnvelope.approval_for` hands
its columns to `brain.browsing.approval.approved`, the same function a suspension in memory
goes through.

Task ids: M19.2.3
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.browsing.approval import (
    ENVELOPE_DIGEST_ARGUMENT,
    EnvelopeApproval,
    approved,
)
from brain.browsing.envelope import Envelope, seal
from brain.browsing.targets import Verb
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ApprovalState, SuspendedAction
from brain.tables.browsing import BrowserEnvelopeRow

#: Why a row that disagrees with its digest is refused rather than repaired.
A_ROW_THAT_DISAGREES_WITH_ITS_DIGEST_WAS_EDITED_AFTER_IT_WAS_SEALED: Final = (
    "The digest is what a person approved and the sealed parts are what a policy is compiled "
    "from. A row where the two differ permits something other than what was approved, and "
    "neither half can be trusted to say which one is right. Refusing to read it stops a "
    "container starting on it; recomputing the digest would approve the edit."
)


class EnvelopeStoreError(Exception):
    """A stored envelope could not be written, read or decided as asked."""


def sealed_parts(envelope: Envelope) -> dict[str, Any]:
    """The permitted parts of an envelope, as the JSON the row holds. Order kept where it counts."""
    return {
        "origins": sorted(envelope.origins),
        "steps": [[step.surface, step.verb.value] for step in envelope.steps],
        "budget": [[verb.value, count] for verb, count in envelope.budget],
        "tiers": [[verb.value, int(tier)] for verb, tier in envelope.tiers],
        "unattended": [[surface, verb.value] for surface, verb in envelope.unattended],
    }


@dataclass(frozen=True)
class StoredEnvelope:
    """One row, read back and checked against its own digest before anything may use it."""

    run_id: str
    target: str
    agent_id: str
    asked_by: str
    envelope_digest: str
    origins: frozenset[str]
    steps: tuple[tuple[str, Verb], ...]
    budget: tuple[tuple[Verb, int], ...]
    tiers: tuple[tuple[Verb, AutonomyTier], ...]
    unattended: tuple[tuple[str, Verb], ...]
    approval_state: ApprovalState | None = None
    raised_at: datetime | None = None
    expires_at: datetime | None = None
    decided_by: str = ""
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        derived = seal(
            run_id=self.run_id,
            origins=self.origins,
            steps=self.steps,
            budget=self.budget,
            tiers=self.tiers,
            unattended=self.unattended,
        )
        if derived != self.envelope_digest:
            msg = (
                f"the stored envelope for run {self.run_id!r} no longer matches its digest. "
                f"{A_ROW_THAT_DISAGREES_WITH_ITS_DIGEST_WAS_EDITED_AFTER_IT_WAS_SEALED}"
            )
            raise EnvelopeStoreError(msg)

    def approval_for(self, envelope: Envelope) -> EnvelopeApproval | None:
        """The approval this row grants the envelope in front of the compiler, or `None`."""
        return approved(
            envelope,
            run_id=self.run_id,
            digest=self.envelope_digest,
            state=self.approval_state,
            decided_by=self.decided_by,
            decided_at=self.decided_at,
            expires_at=self.expires_at,
        )


def stored_from(row: Mapping[str, Any]) -> StoredEnvelope:
    """A row's columns as a checked value. Raises if the row disagrees with its digest."""
    sealed = row["sealed"]
    state = row["approval_state"]
    return StoredEnvelope(
        run_id=row["run_id"],
        target=row["target"],
        agent_id=row["agent_id"],
        asked_by=row["asked_by"],
        envelope_digest=row["envelope_digest"],
        origins=frozenset(sealed["origins"]),
        steps=tuple((surface, Verb(verb)) for surface, verb in sealed["steps"]),
        budget=tuple((Verb(verb), int(count)) for verb, count in sealed["budget"]),
        tiers=tuple((Verb(verb), AutonomyTier(int(tier))) for verb, tier in sealed["tiers"]),
        unattended=tuple((surface, Verb(verb)) for surface, verb in sealed["unattended"]),
        approval_state=ApprovalState(state) if state is not None else None,
        raised_at=row["raised_at"],
        expires_at=row["expires_at"],
        decided_by=row["decided_by"] or "",
        decided_at=row["decided_at"],
    )


def row_values(
    envelope: Envelope,
    *,
    agent_id: str,
    suspension: SuspendedAction | None,
) -> dict[str, Any]:
    """What `put_envelope` writes, refusing an envelope and a suspension that do not belong.

    An envelope that waits for a person is stored with the pending suspension raised for it, and
    one that does not is stored with none. Either mismatch is refused: a waiting envelope with no
    approval raised is a run nobody will ever be asked about, and a suspension on an envelope that
    needs none is a card approving reading.
    """
    if envelope.awaits_approval() != (suspension is not None):
        msg = f"run {envelope.run_id!r} " + (
            "waits for a person and was stored with no approval raised"
            if suspension is None
            else "waits for nobody and was stored with an approval raised"
        )
        raise EnvelopeStoreError(msg)
    values: dict[str, Any] = {
        "run_id": envelope.run_id,
        "target": envelope.plan.request.target,
        "agent_id": agent_id,
        "asked_by": envelope.plan.request.goal.asked_by,
        "envelope_digest": envelope.digest(),
        "sealed": sealed_parts(envelope),
    }
    if suspension is not None:
        carried = suspension.action.args.get(ENVELOPE_DIGEST_ARGUMENT, "")
        if suspension.id != envelope.run_id or carried != values["envelope_digest"]:
            msg = f"the approval raised with run {envelope.run_id!r} is for another envelope"
            raise EnvelopeStoreError(msg)
        if suspension.state is not ApprovalState.PENDING:
            msg = (
                f"the approval for run {envelope.run_id!r} was decided before the envelope was "
                "stored, so the decision has no row to be recorded against"
            )
            raise EnvelopeStoreError(msg)
        values |= {
            "approval_state": ApprovalState.PENDING.value,
            "raised_at": suspension.raised_at,
            "expires_at": suspension.expires_at,
        }
    return values


async def put_envelope(
    session: AsyncSession,
    envelope: Envelope,
    *,
    agent_id: str,
    suspension: SuspendedAction | None = None,
) -> None:
    """Write a sealed envelope once. Does not commit. A second write for the run raises."""
    values = row_values(envelope, agent_id=agent_id, suspension=suspension)
    await session.execute(insert(BrowserEnvelopeRow).values(**values))


async def load_envelope(session: AsyncSession, run_id: str) -> StoredEnvelope | None:
    """The stored envelope for a run, checked against its digest, or `None` when there is none."""
    result = await session.execute(
        select(BrowserEnvelopeRow.__table__).where(BrowserEnvelopeRow.run_id == run_id)
    )
    row = result.mappings().one_or_none()
    return None if row is None else stored_from(dict(row))


async def record_decision(session: AsyncSession, suspension: SuspendedAction) -> None:
    """Record a decided suspension against its pending envelope. Does not commit.

    The ledger entry is `brain.console.approvals.decide`'s and is written before the suspension
    it returns has moved; this writes the row's half. Nothing changed means the run has no
    pending envelope at this digest, and that is said without saying which of absent, decided
    or altered it was.
    """
    if suspension.state is ApprovalState.PENDING or suspension.decided_at is None:
        msg = f"suspension {suspension.id!r} has not been decided, so there is nothing to record"
        raise EnvelopeStoreError(msg)
    # `CursorResult` rather than `Result`, which is what an UPDATE returns and is the only one
    # carrying `rowcount`. Cast at a library boundary where proving the match buys nothing.
    changed = cast(
        "CursorResult[Any]",
        await session.execute(
            update(BrowserEnvelopeRow)
            .where(
                BrowserEnvelopeRow.run_id == suspension.id,
                BrowserEnvelopeRow.approval_state == ApprovalState.PENDING.value,
                BrowserEnvelopeRow.envelope_digest
                == suspension.action.args.get(ENVELOPE_DIGEST_ARGUMENT, ""),
            )
            .values(
                approval_state=suspension.state.value,
                decided_by=suspension.decided_by,
                decided_at=suspension.decided_at,
            )
        ),
    )
    if changed.rowcount != 1:
        msg = (
            f"run {suspension.id!r} has no pending envelope at the digest that was decided, so "
            "the decision was not recorded"
        )
        raise EnvelopeStoreError(msg)
