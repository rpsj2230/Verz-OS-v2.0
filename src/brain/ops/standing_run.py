"""The staff sync's standing step: disable whom the list keeps out, enable whom it lets back in.

`brain.identity.standing` decides; this reads what that decision needs out of the install and
carries it out through `StoredPrincipalStates.set_disabled`, the People screen's own write, so the
disabling, the ended sessions (0003's cascade) and the ledger entry (0095b) are the ones a person's
press would leave, attributed to the source's sync.

**Who last changed a person is the ledger's `principal_state` entry.** The list lets back in only
whom it kept out, and the one record of who disabled somebody is the entry the trigger writes
beside the change, in the same transaction, naming the actor. Rejected: a column saying the list
did it, which would be a second record of one fact that a hand edit could leave disagreeing with
the first, and a migration for something the ledger already holds.

**It is planned before the roster is written and carried out after the accounts step**, in
`brain.ops.staff_sync_run`, for `ACCOUNTS_ARE_MADE_BEFORE_THE_ROSTER_IS_WRITTEN`'s reason: the run
row is append-only, so what this did is on it only if it ran first. It is planned twice, once so
the accounts step knows whose account to keep open as the last administrator, and again after the
accounts step has joined new people to their rows, and it never raises.

Task ids: M1.6.14
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.identity.organisation_sync import sync_actor, sync_trace
from brain.identity.principal_state_store import StoredPrincipalStates
from brain.identity.sign_in_binding import SignInBindings
from brain.identity.staff_source import EmploymentType
from brain.identity.standing import Held, Standing, StandingPlan, standing_plan
from brain.ops.head_audit_store import bound_principals
from brain.tables.audit import AuditEntryRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()

#: The ledger's action for a change to whether somebody is disabled, and the two changes.
STATE_ACTION: Final = "principal_state"
STATE_CHANGES: Final = ("disabled", "enabled")

#: The digest the sync's own ledger entries carry for a reach: a sync has none.
NO_REACH: Final = "0" * 32


def _subject(principal_id: str) -> str:
    return f"principal:{principal_id}"


async def plan_standing(
    sessions: async_sessionmaker[AsyncSession],
    *,
    source: str,
    standings: Mapping[str, Standing],
    allowed: Collection[EmploymentType],
    now: datetime,
) -> StandingPlan:
    """Read who the list can speak for, how each stands and who last changed them, and plan."""
    actor = sync_actor(source)
    async with sessions() as session, session.begin():
        bound = {
            str(digest): str(principal)
            for digest, principal in (
                await session.execute(bound_principals(list(standings)))
            ).all()
        }
        principals = sorted(set(bound.values()))
        disabled = {
            str(pid): at is not None
            for pid, at in (
                await session.execute(
                    select(PrincipalRow.id, PrincipalRow.disabled_at).where(
                        PrincipalRow.id.in_(principals), PrincipalRow.deleted_at.is_(None)
                    )
                )
            ).all()
        }
        last = {
            str(subject): (str(by), str((details or {}).get("change", "")))
            for subject, by, details in (
                await session.execute(
                    select(AuditEntryRow.subject, AuditEntryRow.actor_id, AuditEntryRow.details)
                    .where(
                        AuditEntryRow.action == STATE_ACTION,
                        AuditEntryRow.subject.in_([_subject(one) for one in disabled]),
                        AuditEntryRow.details["change"].astext.in_(STATE_CHANGES),
                    )
                    .distinct(AuditEntryRow.subject)
                    .order_by(AuditEntryRow.subject, AuditEntryRow.seq.desc())
                )
            ).all()
        }
    administrators = await SignInBindings(sessions, "").administrators_linked(now)
    held = {
        pid: Held(
            principal_id=pid,
            disabled=is_disabled,
            changed_by_the_list=last.get(_subject(pid)) == (actor, "disabled"),
        )
        for pid, is_disabled in disabled.items()
    }
    return standing_plan(
        standings, bound=bound, held=held, administrators=administrators, allowed=allowed
    )


async def apply_standing(
    sessions: async_sessionmaker[AsyncSession],
    plan: StandingPlan,
    *,
    source: str,
    now: datetime,
) -> None:
    """Disable and enable as planned, under the source's sync. One person per transaction."""
    states = StoredPrincipalStates(sessions)
    actor, trace_id = sync_actor(source), sync_trace("staff-standing", now)
    changes = [(pid, True) for pid, _ in plan.to_disable] + [(pid, False) for pid in plan.to_enable]
    for principal_id, disabled in changes:
        await states.set_disabled(
            principal_id,
            disabled=disabled,
            may=lambda _department: True,
            by=actor,
            ent_hash=NO_REACH,
            trace_id=trace_id,
        )
