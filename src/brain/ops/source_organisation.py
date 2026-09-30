"""The departments a staff source names, founded on a person's word, and the sync's placements.

Found on the owner's install on 2026-09-29: a Lark staff sync placed 116 of 123 people in eleven
departments named by Lark, and the Departments and teams screen showed nothing, because
`gate.department` was empty and nothing would ever fill it. `brain.identity.organisation_sync`
said a department no registered row carries is never created and that nothing applied its plan on
a schedule. Both halves are here, with no judgement: `organisation_sync` decides, the stores write.

**Founding is a person's act, offered from what the source names.** `named_departments` reads the
department names the chosen source's live roster rows carry and the departments already registered,
and `organisation_sync.departments_to_found` says which to offer, each with its slug. `found_named`
founds exactly the ones the person confirmed and are still offered, one department and its scope at
a time through `StoredOrganisation.found_department`, the Departments screen's own write, whose
`0086` triggers put every department and scope on the ledger under the person who pressed. A second
press founds nothing, because every name then answers to a registered department. See
`brain.identity.organisation_sync.A_DEPARTMENT_IS_FOUNDED_BY_A_PERSON_FROM_WHAT_THE_SOURCE_NAMES`.

**Placing is the sync's, every run, under the plan's rules.** `apply_organisation` compares the
roster with what the install holds, matching the source's spelling of a department to the
registered one, and applies the plan through `StoredOrganisation.apply_sync`: team memberships and
department leads the source names are made, and only placements this source's sync made are ended,
on the plan's own conditions (a complete list, applied before, or the source saying somebody left).
A department two people claim to lead gets neither.

**What a sync places, and what it does not yet.** A person's reach in a department is their
Starter pack, which `brain.ops.starter_pack_store` has granted by department since 2026-09-28 and
which follows a mover; a department lead's audit reach is `brain.ops.head_audit_store`'s; team
memberships and leads are this. A principal's `primary_department`, which the Departments screen
lists people under, is written by no sync yet: it keeps no record of who set it, so a sync
writing it would end placements it never made. The owner decided on 2026-09-29 that an install
chooses whether departments come from the staff source or are managed in the console; placing
people's departments from the source is that setting's staff-source half, and is built with it.

Rejected: founding the departments inside the nightly run. See the constant named above.

Task ids: M27.7.4, M1.6.12
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.console.organisation import founded
from brain.identity.organisation_store import Attribution, StoredOrganisation, StructureRecords
from brain.identity.organisation_sync import (
    DepartmentsNamed,
    DepartmentToFound,
    OrganisationPlan,
    departments_to_found,
    organisation_plan,
)
from brain.identity.staff_source import Roster
from brain.identity.starter_pack_sync import registered_by_name
from brain.ops.staff_sync_store import department_names_listed
from brain.ops.starter_pack_store import registered_departments


@dataclass(frozen=True)
class Founded:
    """What one press founded, and the names it could not found, in the source's spelling."""

    created: tuple[DepartmentToFound, ...]
    not_founded: tuple[str, ...]


async def _registered(session: AsyncSession) -> dict[str, str]:
    return {
        str(slug): str(name) for slug, name in (await session.execute(registered_departments()))
    }


async def named_departments(
    sessions: async_sessionmaker[AsyncSession], source: str
) -> DepartmentsNamed:
    """The departments to offer for founding from what `source`'s live roster rows name."""
    async with sessions() as session, session.begin():
        names = [
            str(one) for one in (await session.execute(department_names_listed(source))).scalars()
        ]
        registered = await _registered(session)
    return departments_to_found(names, registered, registered_by_name(registered))


async def found_named(
    store: StructureRecords,
    named: DepartmentsNamed,
    *,
    confirmed: Collection[str],
    by: Attribution,
) -> Founded:
    """Found each offered department whose slug the person confirmed, one at a time.

    A slug confirmed and no longer offered is not founded: the page it was confirmed on is older
    than the install. A department the store refuses, a name taken in the moment between, is named
    in `not_founded` and the rest are still founded, because each is a department of its own.
    """
    created: list[DepartmentToFound] = []
    not_founded: list[str] = []
    for one in named.to_found:
        if one.slug not in confirmed:
            continue
        try:
            department, scope = founded(one.slug, one.name)
        except ValueError:
            not_founded.append(one.name)
            continue
        done = await store.found_department(department=department, scope=scope, by=by)
        if isinstance(done, datetime):
            created.append(one)
        else:
            not_founded.append(one.name)
    return Founded(created=tuple(created), not_founded=tuple(not_founded))


async def apply_organisation(
    sessions: async_sessionmaker[AsyncSession],
    roster: Roster,
    *,
    known: Mapping[str, str],
    last_applied: datetime | None,
    trace_id: str,
) -> OrganisationPlan:
    """Plan the team memberships and leads this roster supports and apply them, as the source.

    The plan is returned whether or not it was applied: a plan the store may not apply (a source
    not trusted with departments) or one that changes nothing writes nothing.
    """
    store = StoredOrganisation(sessions)
    memberships, leads, teams, departments = await store.sync_holdings()
    async with sessions() as session, session.begin():
        registered = await _registered(session)
    plan = organisation_plan(
        roster,
        known=known,
        teams=teams,
        departments=departments,
        memberships=memberships,
        leads=leads,
        last_applied=last_applied,
        slug_of=registered_by_name(registered),
    )
    if plan.safe_to_apply and not plan.changes_nothing:
        await store.apply_sync(plan, trace_id=trace_id)
    return plan
