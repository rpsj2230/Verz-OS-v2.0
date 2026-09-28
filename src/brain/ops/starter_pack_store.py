"""Giving each synced person the Starter pack for their own department, on every scheduled read.

`brain.identity.starter_pack_sync.starter_plan` decides who holds which department's Starter pack
(needs-rupash item 105); this reads what it needs, hands it over and writes what comes back, and
holds no judgement. `brain.ops.staff_sync_run` calls it after the roster's transaction and the
heads' audit reach have committed, in a transaction of its own, for
`head_audit_store`'s reason: a failure here leaves every joiner and leaver applied and the packs
one run stale, and never takes the staff list with it.

**Retirements first, then assignments.** `gate.capability_pack_assignment` holds one live row per
person and pack, so a mover's old department's pack is retired before the new one is inserted,
in the same transaction, and nobody is ever between two packs or holding none.

**Everything goes on the ledger, by the trigger and never by this module.** `0003`'s
`capability_pack_assignment_is_audited` appends a `grant` for every insert and a `revoke` for
every retirement, naming the pack; with no person attributed it records `granted_by`, which is
`roster.<source>`, as the actor, exactly as for the heads' audit grants. The same insert bumps the
person's grants version, so their next request resolves the new reach with no reindex.
`brain.ops.write_attribution` excuses the run's caller for the reason it excuses the heads'.

Task ids: M26.1.2, M26.1.3, M26.2.6
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Insert, Select, Update, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.core.principal import Employment, PrincipalKind
from brain.core.scope import Scope
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.packs import PackAssignment
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import Roster
from brain.identity.staff_sync import ROSTER_PREFIX
from brain.identity.starter_pack_sync import HeldStarter, StarterPlan, starter_plan
from brain.identity.teams import PrincipalSubject
from brain.ops.head_audit_store import bound_principals, known_from
from brain.ops.staff_sync_store import leavers_principals
from brain.tables.gate import CapabilityPackAssignmentRow, CapabilityPackRow, DepartmentRow
from brain.tables.identity import PrincipalRow

#: The employments that hold a standing entitlement. A partner holds none and acts through a
#: break-glass session, and a service is not a person the roster lists.
STANDING_EMPLOYMENTS: tuple[str, ...] = (Employment.STAFF.value, Employment.CONTRACTOR.value)


def the_starter_pack() -> Select[tuple[uuid.UUID, list[str]]]:
    """The live Starter pack's id and capabilities, as the furnishing wrote it."""
    return select(CapabilityPackRow.id, CapabilityPackRow.capabilities).where(
        CapabilityPackRow.name == STARTER_PACK.slug, CapabilityPackRow.deleted_at.is_(None)
    )


def registered_departments() -> Select[tuple[str, str]]:
    """Every live department's slug and name."""
    return select(DepartmentRow.slug, DepartmentRow.name).where(DepartmentRow.deleted_at.is_(None))


def standing_principals(principal_ids: Sequence[str]) -> Select[tuple[str]]:
    """Which of these principals is a person who may hold a standing entitlement."""
    return select(PrincipalRow.id).where(
        PrincipalRow.id.in_(sorted(set(principal_ids))),
        PrincipalRow.kind == PrincipalKind.HUMAN.value,
        PrincipalRow.employment.in_(STANDING_EMPLOYMENTS),
    )


def starter_assignments(pack_id: uuid.UUID) -> Select[tuple[str, dict[str, Any], str]]:
    """Every live assignment of the Starter pack, whoever gave it."""
    return select(
        CapabilityPackAssignmentRow.principal_id,
        CapabilityPackAssignmentRow.scope,
        CapabilityPackAssignmentRow.granted_by,
    ).where(
        CapabilityPackAssignmentRow.pack_id == pack_id,
        CapabilityPackAssignmentRow.deleted_at.is_(None),
    )


def assign(assignment: PackAssignment, principal_id: str, pack_id: uuid.UUID) -> Insert:
    """The INSERT for one assignment, the columns `govern_pack_routes.add_assignment` writes."""
    return insert(CapabilityPackAssignmentRow).values(
        principal_id=principal_id,
        pack_id=pack_id,
        scope=assignment.scope.model_dump(mode="json"),
        granted_by=assignment.granted_by,
        reason=assignment.reason,
        not_after=assignment.not_after,
    )


def retire(held: HeldStarter, pack_id: uuid.UUID) -> Update:
    """Retire one assignment a sync gave, stamped by its own statement for `0045`'s policy.

    The granter is in the WHERE clause as well as in the plan's decision, so a row a person
    assigned in the moment between the read and this write is not the one retired.
    """
    return (
        update(CapabilityPackAssignmentRow)
        .where(
            CapabilityPackAssignmentRow.principal_id == held.principal_id,
            CapabilityPackAssignmentRow.pack_id == pack_id,
            CapabilityPackAssignmentRow.deleted_at.is_(None),
            CapabilityPackAssignmentRow.granted_by == held.granted_by,
            CapabilityPackAssignmentRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True),
        )
        .values(deleted_at=func.statement_timestamp())
    )


def writes_for(plan: StarterPlan, pack_id: uuid.UUID) -> list[Any]:
    """The statements a plan becomes, retirements first. Nothing when it was refused."""
    if not plan.safe_to_apply:
        return []
    statements: list[Any] = [retire(one, pack_id) for one in plan.to_retire]
    statements.extend(
        assign(one, one.subject.principal_id, pack_id)
        for one in plan.to_assign
        if isinstance(one.subject, PrincipalSubject)
    )
    return statements


async def grant_starter_packs(
    session: AsyncSession, roster: Roster, *, read_at: datetime
) -> StarterPlan:
    """Read, decide and write every synced person's Starter pack, in the session's transaction."""
    found = (await session.execute(the_starter_pack())).first()
    pack_id: uuid.UUID | None = None if found is None else found[0]
    departments = {
        str(slug): str(name) for slug, name in (await session.execute(registered_departments()))
    }
    digests = [digest_of(one.work_address) for one in roster.people]
    bound = {
        str(digest): str(principal)
        for digest, principal in (await session.execute(bound_principals(digests))).all()
    }
    known = known_from(roster, bound)
    standing = frozenset(
        str(one)
        for one in (await session.execute(standing_principals(list(known.values())))).scalars()
    )
    held = (
        ()
        if pack_id is None
        else tuple(
            HeldStarter(
                principal_id=str(principal),
                scope=Scope.model_validate(scope),
                granted_by=str(granted_by),
            )
            for principal, scope, granted_by in (
                await session.execute(starter_assignments(pack_id))
            ).all()
        )
    )
    leavers = frozenset(str(one) for one in (await session.execute(leavers_principals())).scalars())
    plan = starter_plan(
        roster,
        known=known,
        standing=standing,
        departments=departments,
        held=held,
        leavers=leavers,
        pack=None if found is None else tuple(found[1]),
        read_at=read_at,
    )
    if pack_id is not None:
        for statement in writes_for(plan, pack_id):
            await session.execute(statement)
    return plan
