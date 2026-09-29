"""The install acceptance checks for the organisation a staff source names: founded, then placed.

Found on the owner's install on 2026-09-29: the Lark staff sync placed people in eleven
departments Lark named, and the Departments and teams screen stayed empty, because nothing founded
a department from a source and nothing applied the organisation plan on a schedule.
`brain.ops.source_organisation` is both halves, and these checks drive it against the install's own
schema, as the application role, in the harness's transaction, which is always rolled back.

**Everything is in the reserved departments and under reserved names.** The staff source the
checks list people from is named `acceptance`, which no install chooses, so the names it offers are
only the two reserved departments' names, spelled as a directory would spell them (`Acceptance A`),
and the slugs the product gives them are the reserved slugs. The people are reserved principals,
joined to their roster rows by the addresses the check makes up, never bound to a sign-in.

**Two checks, one per half, because each half is one flow on its own screen.** The founding is a
person's act on Departments and teams; the placing is the nightly run's. Rejected: one check doing
both, which would report one red row for two different breakages.

Task ids: M38.5.1, M27.7.4, M1.6.12
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import insert, select

from brain.console.organisation import founded
from brain.identity.organisation_store import Attribution, StoredOrganisation
from brain.identity.organisation_sync import sync_actor
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import Asserts, Roster, StaffRecord
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.ops.source_organisation import apply_organisation, found_named, named_departments
from brain.tables.audit import AuditEntryRow
from brain.tables.gate import DepartmentRow
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow
from brain.tables.staff import StaffMemberRow

#: The staff source the checks list people from. No install chooses a source by this name.
SOURCE = "acceptance"

#: How a directory would spell each reserved department: `acceptance_a` is `Acceptance A`.
SPELLED = {slug: f"Acceptance {slug.rsplit('_', 1)[-1].upper()}" for slug in RESERVED_DEPARTMENTS}

#: The team the placing check makes in the first reserved department.
TEAM = "checked"


def _address(h: Harness, principal_id: str) -> str:
    """A made-up work address for a reserved principal, on a domain nothing delivers to."""
    return f"{principal_id.replace('.', '-')}-{h.run}@acceptance.invalid"


async def _listed(h: Harness, address: str, department: str) -> None:
    await h.execute(
        insert(StaffMemberRow).values(
            source=SOURCE,
            address_hash=digest_of(address),
            display_name="Acceptance check",
            department=department,
            first_listed_at=h.now,
            last_listed_at=h.now,
        )
    )


def _by(h: Harness) -> Attribution:
    return Attribution(actor=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id)


@check(
    leaves=("M27.7.4",),
    sentence=(
        "The departments a staff source names are offered on Departments and teams with the short "
        "name each would get, two spellings of one name as one; the one confirmed is founded with "
        "its scope and put in the ledger under the person who pressed; a second press founds "
        "nothing already founded, and a name a leaver alone carries is never offered."
    ),
)
async def departments_a_staff_source_names_are_founded_once(h: Harness) -> None:
    first, second = RESERVED_DEPARTMENTS
    for one, spelled in (("one", SPELLED[first]), ("two", SPELLED[first].lower())):
        await _listed(h, _address(h, h.principal(first, one)), spelled)
    await _listed(h, _address(h, h.principal(second, "one")), SPELLED[second])
    await h.execute(
        insert(StaffMemberRow).values(
            source=SOURCE,
            address_hash=digest_of(_address(h, h.principal(second, "gone"))),
            display_name="Acceptance check",
            department="Acceptance Left",
            first_listed_at=h.now,
            last_listed_at=h.now,
            left_at=h.now,
            left_because="source_says_left",
        )
    )
    offered = await named_departments(h.sessions, SOURCE)
    if [(one.name, one.slug) for one in offered.to_found] != [
        (SPELLED[first], first),
        (SPELLED[second], second),
    ]:
        raise CheckFailedError(
            "the departments the source names were not offered once each under the reserved slugs"
        )

    store = StoredOrganisation(h.sessions)
    done = await found_named(store, offered, confirmed={first}, by=_by(h))
    if [one.slug for one in done.created] != [first] or done.not_founded:
        raise CheckFailedError("the one department confirmed was not the one founded")
    founded = (
        (
            await h.execute(
                select(DepartmentRow.name).where(
                    DepartmentRow.slug == first, DepartmentRow.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    if list(founded) != [SPELLED[first]]:
        raise CheckFailedError("the founded department does not carry the name the source used")
    ledger = (
        (
            await h.execute(
                select(AuditEntryRow.actor_id).where(AuditEntryRow.subject == f"department:{first}")
            )
        )
        .scalars()
        .all()
    )
    if list(ledger) != [h.actor]:
        raise CheckFailedError("the founding is not in the ledger under the person who pressed")

    again = await named_departments(h.sessions, SOURCE)
    if [one.slug for one in again.to_found] != [second] or SPELLED[first] not in again.registered:
        raise CheckFailedError("a founded department was offered again")
    twice = await found_named(store, again, confirmed={first, second}, by=_by(h))
    if [one.slug for one in twice.created] != [second]:
        raise CheckFailedError("a second press founded a department that was already founded")


@check(
    leaves=("M27.7.4", "M1.6.12"),
    sentence=(
        "The staff sync places a person in the team and as the lead their source names, matching "
        "the source's spelling of the department to the founded one, as the source's actor; a "
        "department two people claim to lead gets neither; on the next complete run a person the "
        "source moved leaves the team and the lead, and a placement a person made stays."
    ),
)
async def the_staff_sync_places_people_where_its_source_says(h: Harness) -> None:
    from brain.identity.teams import Team

    first, second = RESERVED_DEPARTMENTS
    store = StoredOrganisation(h.sessions)
    # Founded with the names the source spells, as the founding check leaves them, so the match
    # this check proves is the name's and the slug's both.
    for slug in RESERVED_DEPARTMENTS:
        record, scope = founded(slug, SPELLED[slug])
        if not isinstance(
            await store.found_department(department=record, scope=scope, by=_by(h)), datetime
        ):
            raise CheckFailedError("a reserved department could not be founded")
    added = await store.add_team(
        team=Team(company_id="company", department_slug=first, slug=TEAM, name="Checked"),
        by=_by(h),
    )
    if isinstance(added, str):
        raise CheckFailedError("the check's team could not be added to a reserved department")
    mover, stayer = h.principal(first, "one"), h.principal(first, "two")
    claimants = (h.principal(second, "one"), h.principal(second, "two"))
    for pid, department in ((mover, first), (stayer, first), *((one, second) for one in claimants)):
        await h.person(pid, department=department)
    placed = await store.place(
        department=first,
        team=TEAM,
        principal_id=stayer,
        actor=h.actor,
        ent_hash=SET_UP_REACH,
        trace_id=h.trace_id,
        may=lambda _: True,
    )
    if placed is None:
        raise CheckFailedError("a placement made by a person could not be written")

    known = {_address(h, pid): pid for pid in (mover, stayer, *claimants)}
    trusted = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT})
    claims = tuple(
        StaffRecord(_address(h, one), "Acceptance check", department=SPELLED[second], leads=True)
        for one in claimants
    )
    before = Roster(
        source=SOURCE,
        complete=True,
        asserts=trusted,
        people=(
            StaffRecord(
                _address(h, mover),
                "Acceptance check",
                department=SPELLED[first].lower(),
                teams=(TEAM,),
                leads=True,
            ),
            *claims,
        ),
    )
    plan = await apply_organisation(
        h.sessions, before, known=known, last_applied=None, trace_id=h.trace_id
    )
    if plan.unregistered or plan.contested != (second,):
        raise CheckFailedError("the source's spelling was not matched, or a contested lead passed")
    sync = sync_actor(SOURCE)
    if await _members(h) != {(mover, sync, None), (stayer, h.actor, None)}:
        raise CheckFailedError("the sync did not place the person in the team the source named")
    if await _leads(h) != {(first, mover, sync, None)}:
        raise CheckFailedError(
            "the lead the source named was not appointed, or a contested one was"
        )

    after = Roster(
        source=SOURCE,
        complete=True,
        asserts=trusted,
        people=(StaffRecord(_address(h, mover), "Acceptance check", department=SPELLED[second]),),
    )
    await apply_organisation(
        h.sessions, after, known=known, last_applied=h.now, trace_id=h.trace_id
    )
    if await _members(h) != {(mover, sync, sync), (stayer, h.actor, None)}:
        raise CheckFailedError("a mover kept their team, or a placement a person made was ended")
    if await _leads(h) != {(first, mover, sync, sync)}:
        raise CheckFailedError("a lead the source no longer names was not stood down")


async def _members(h: Harness) -> set[tuple[str, str, str | None]]:
    """Every placement in the reserved team, live or ended, as person, placer and ender."""
    found = await h.execute(
        select(
            TeamMembershipRow.principal_id, TeamMembershipRow.added_by, TeamMembershipRow.ended_by
        ).where(TeamMembershipRow.principal_id.startswith(f"acceptance.{h.run}."))
    )
    return {(str(p), str(a), None if e is None else str(e)) for p, a, e in found.all()}


async def _leads(h: Harness) -> set[tuple[str, str, str, str | None]]:
    """Every lead of a reserved department, live or ended."""
    found = await h.execute(
        select(
            DepartmentRow.slug,
            DepartmentLeadRow.principal_id,
            DepartmentLeadRow.appointed_by,
            DepartmentLeadRow.ended_by,
        )
        .join(DepartmentRow, DepartmentRow.id == DepartmentLeadRow.department_id)
        .where(DepartmentRow.slug.in_(RESERVED_DEPARTMENTS))
    )
    return {(str(d), str(p), str(a), None if e is None else str(e)) for d, p, a, e in found.all()}
