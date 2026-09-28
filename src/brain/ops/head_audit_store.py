"""Rewriting every department head's audit reach from the staff list, on every scheduled read.

Needs Rupash item 48 was decided Option A on 2026-09-09: a department head reads their department's
activity through audit grants written against the people placed in it, rewritten by the staff sync
when somebody joins or leaves, and no audit entry records a department. `brain.identity.staff_sync.
audit_reach_for_head` has computed those grants since then and nothing applied them, because no
sync applied anything; `brain.ops.staff_sync_run` has applied the roster since 2026-09-21, and this
is the half that applies the heads' reach after it. **It is Option A and never Option B**: the
grants name principals under `actor_id IN (...)`, and nothing here or anywhere writes a department
onto an entry.

**Who is a head is the install's, not the source's.** A head is a live row in
`gate.department_lead`, which a person appoints on the Departments screen or the organisation sync
writes for a trusted source. Reading leads from the roster instead would let a spreadsheet make
somebody an auditor of fifteen people by typing their name in a column; the lead table is the
decision a person reviewed.

**The members are the roster's people this install already knows**, matched by the email binding
`auth.principal_identity` holds, whose digest is the one `auth.staff_member` keeps. Somebody the
roster names and nobody has bound contributes nothing, which is `_members_of`'s argument: they are
reported once, as somebody the sync would add, and not a second time here.

**Three writes, and the sync ends only what it made.** A grant the roster wrote and no longer wants
is retired; a grant it wants and does not hold is inserted; one it holds and still wants has its
lapse moved on by `renewed`, because a roster grant lapses two sync intervals after its last
reading and a head whose people did not change must not lose them. A capability the head already
holds live from somebody else, an administrator's company-wide audit read say, is left alone and
not written again: the table holds one live grant per person and capability, and a person's grant
is not the sync's to replace. `audit_reach_for_head` only ever proposes deleting roster grants.

**A failure here never undoes the roster.** The caller runs this in its own transaction after the
roster's has committed and logs a failure rather than raising it, so a head's reach that cannot be
written leaves the staff list applied and the reach as it was, stale by one run, which is
`THE_STALENESS_WINDOW` and not a new failure. The opposite order, one transaction for both, would
let a unique-index race on one head's grant take every joiner and leaver with it.

**A former head keeps nothing the roster gave them.** The rewrite walks live leads, so a lead
stood down, a department retired or a head the roster marks as having left would otherwise keep
reading their old people until the lapse. Every sync-written audit grant held by somebody who is
not a live head is retired in the run that finds them. See `A_FORMER_HEAD_KEEPS_NOTHING`.

**A head of several departments is one reach**, for `audit_reach_for_head`'s reason: one per
department, each run would retire what the one before it wrote.

The ledger entries are the grant trigger's (`0003`): an insert is a grant and a retirement a
revocation, attributed to `granted_by`, which is `roster.<source>`, because a scheduled run has no
person and no reach. `brain.ops.write_attribution` excuses this path for that reason. It was
`roster:<source>` until the ledger's actor grammar was found to refuse the colon, which rolled
every rewrite back on a real database; see `staff_sync.A_SYNCS_GRANTOR_IS_THE_LEDGERS_ACTOR`.

Task ids: M1.8.3
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Insert, Update, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.core.entitlement import Capability
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.identity.packs import SubjectGrant
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import Roster
from brain.identity.staff_sync import (
    AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE,
    ROSTER_PREFIX,
    HeadAuditReach,
    audit_reach_for_head,
    renewed,
)
from brain.identity.teams import PrincipalSubject
from brain.ops.staff_sync_store import leavers_principals
from brain.tables.gate import CapabilityGrantRow, DepartmentRow
from brain.tables.identity import PrincipalIdentityRow
from brain.tables.organisation import DepartmentLeadRow

#: Why the grants a sync gave somebody are retired once they are no longer a head.
A_FORMER_HEAD_KEEPS_NOTHING: Final = (
    "Revocation is the deletion of a grant, and the rewrite walks live leads, so a lead stood "
    "down, a department retired or a head the roster marks as having left is never looked at "
    "again. Left alone, their sync-written audit grants would go on reading their old people "
    "until the lapse two sync intervals later. So every such grant held by somebody who is not "
    "a live head is retired in the run that finds them, and the lapse is only the backstop for "
    "a sync that stops."
)


def leads() -> Any:
    """Every live lead the roster has not marked as having left, with the department's slug."""
    return (
        select(DepartmentLeadRow.principal_id, DepartmentRow.slug)
        .join(DepartmentRow, DepartmentRow.id == DepartmentLeadRow.department_id)
        .where(
            DepartmentLeadRow.ended_at.is_(None),
            DepartmentRow.deleted_at.is_(None),
            DepartmentLeadRow.principal_id.not_in(leavers_principals()),
        )
        .order_by(DepartmentLeadRow.principal_id, DepartmentRow.slug)
    )


def heads_from(rows: Iterable[Sequence[Any]]) -> dict[str, tuple[str, ...]]:
    """Each head and every department they lead, so a head of two is one reach."""
    found: dict[str, list[str]] = {}
    for principal_id, slug in rows:
        found.setdefault(str(principal_id), []).append(str(slug))
    return {head: tuple(sorted(slugs)) for head, slugs in found.items()}


def _roster_audit_grants() -> tuple[Any, ...]:
    """The live audit grants some staff sync wrote, as WHERE conditions."""
    return (
        CapabilityGrantRow.deleted_at.is_(None),
        CapabilityGrantRow.capability.in_(sorted(AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE)),
        CapabilityGrantRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True),
    )


def roster_audit_holders() -> Any:
    """Every principal holding a live audit grant a staff sync wrote."""
    return (
        select(CapabilityGrantRow.principal_id)
        .where(CapabilityGrantRow.principal_id.is_not(None), *_roster_audit_grants())
        .distinct()
    )


def retire_a_former_heads_grants(principal_id: str) -> Update:
    """Retire every live audit grant a sync wrote them. See `A_FORMER_HEAD_KEEPS_NOTHING`."""
    return (
        update(CapabilityGrantRow)
        .where(CapabilityGrantRow.principal_id == principal_id, *_roster_audit_grants())
        .values(deleted_at=func.statement_timestamp())
    )


def bound_principals(digests: Sequence[str]) -> Any:
    """The principal behind each email binding whose digest is one of these."""
    return select(PrincipalIdentityRow.identity_hash, PrincipalIdentityRow.principal_id).where(
        PrincipalIdentityRow.channel == Channel.EMAIL.value,
        PrincipalIdentityRow.deleted_at.is_(None),
        PrincipalIdentityRow.identity_hash.in_(sorted(set(digests))),
    )


def audit_grants_of(principal_id: str) -> Any:
    """Every live audit grant one principal holds, whoever wrote it."""
    return select(CapabilityGrantRow).where(
        CapabilityGrantRow.principal_id == principal_id,
        CapabilityGrantRow.deleted_at.is_(None),
        CapabilityGrantRow.capability.in_(sorted(AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE)),
    )


def insert_grant(grant: SubjectGrant, principal_id: str) -> Insert:
    """The INSERT for one roster grant: the columns `brain.govern_routes.add_grant` writes, with
    the scope rendered as JSON here rather than left to the driver's encoder."""
    return insert(CapabilityGrantRow).values(
        principal_id=principal_id,
        capability=grant.capability.value,
        scope=grant.scope.model_dump(mode="json"),
        granted_by=grant.granted_by,
        reason=grant.reason,
        not_after=grant.not_after,
    )


def retire_roster_grant(principal_id: str, capability: str) -> Update:
    """Retire one live grant the roster wrote, stamped by its own statement for `0045`'s policy."""
    return (
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == capability,
            CapabilityGrantRow.deleted_at.is_(None),
            CapabilityGrantRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True),
        )
        .values(deleted_at=func.statement_timestamp())
    )


def renew_roster_grant(grant: SubjectGrant, principal_id: str) -> Update:
    """Move one live roster grant's lapse on. The trigger records nothing for an update that
    does not retire the row, so a renewal is silent in the ledger, as it should be."""
    return (
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == grant.capability.value,
            CapabilityGrantRow.deleted_at.is_(None),
            CapabilityGrantRow.granted_by == grant.granted_by,
        )
        .values(not_after=grant.not_after)
    )


def held_grant(row: CapabilityGrantRow) -> SubjectGrant:
    """One stored grant as the reach reads it. Loaded by principal, so never a team's."""
    if row.principal_id is None:
        msg = "a team's grant is not a person's reach"
        raise ValueError(msg)
    return SubjectGrant(
        subject=PrincipalSubject(principal_id=row.principal_id),
        capability=Capability(value=row.capability),
        scope=Scope.model_validate(row.scope),
        granted_by=row.granted_by,
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
    )


def known_from(roster: Roster, bound: Mapping[str, str]) -> dict[str, str]:
    """Casefolded work address to principal, for every roster person somebody has bound."""
    return {
        one.work_address.casefold(): bound[digest_of(one.work_address)]
        for one in roster.people
        if digest_of(one.work_address) in bound
    }


def writes_for(
    reach: HeadAuditReach, held: Sequence[SubjectGrant], *, read_at: datetime
) -> list[Any]:
    """The statements one head's reach becomes, retirements first. See the module docstring."""
    if reach.refusals:
        return []
    others = {one.capability.value for one in held if not one.granted_by.startswith(ROSTER_PREFIX)}
    statements: list[Any] = [
        retire_roster_grant(reach.head_id, one.capability.value) for one in reach.to_delete
    ]
    statements.extend(
        insert_grant(one, reach.head_id)
        for one in reach.to_insert
        if one.capability.value not in others
    )
    statements.extend(
        renew_roster_grant(renewed(one, read_at=read_at), reach.head_id) for one in reach.unchanged
    )
    return statements


async def rewrite_head_audit_reach(
    session: AsyncSession, roster: Roster, *, read_at: datetime
) -> tuple[HeadAuditReach, ...]:
    """Apply every live head's audit reach for this roster, in the session's transaction."""
    heads = heads_from((await session.execute(leads())).all())
    holders = (await session.execute(roster_audit_holders())).scalars().all()
    for former in sorted({str(one) for one in holders} - heads.keys()):
        await session.execute(retire_a_former_heads_grants(former))
    if not heads:
        return ()
    digests = [digest_of(one.work_address) for one in roster.people]
    bound = {
        str(digest): str(principal)
        for digest, principal in (await session.execute(bound_principals(digests))).all()
    }
    known = known_from(roster, bound)
    applied: list[HeadAuditReach] = []
    for head_id, slugs in heads.items():
        rows = (await session.execute(audit_grants_of(head_id))).scalars().all()
        held = [held_grant(row) for row in rows]
        reach = audit_reach_for_head(
            roster, department=slugs, head_id=head_id, known=known, read_at=read_at, held=held
        )
        for statement in writes_for(reach, held, read_at=read_at):
            await session.execute(statement)
        applied.append(reach)
    return tuple(applied)
