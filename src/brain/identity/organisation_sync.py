"""What the staff sync would change about teams and leads, and why it would not change the rest.

`brain.identity.staff_source.teams_from` and `leads_from` read where a trusted source says somebody
sits, and `gate.team_membership` and `gate.department_lead` hold where the install says they sit.
This is the difference, computed the way `brain.identity.staff_sync.dry_run` computes the roster's:
from the same inputs the applying step uses, writing nothing, so what a person reads is what would
run. `brain.identity.organisation_store.StoredOrganisation.apply_sync` executes the plan and holds
no judgement.

**Four rules, and every one of them only narrows what the sync may do.**

*A source not trusted with departments proposes nothing.* It is refused, named, and the plan is
empty in both directions, for `staff_sync.A_ROSTER_NOT_TRUSTED_WITH_DEPARTMENTS_NAMES_THE_WRONG_
PEOPLE`'s reason: a wrong team is the directory somebody reviews access against.

*The sync ends only what the sync made.* A placement somebody made from the console is not the
sync's to take away, whatever the source says, so `to_leave` and `to_stand_down` come only from rows
whose actor is this source's, `sync_actor`. A lead appointed by hand is not replaced either: the
department is named in `withheld` and left alone. See `THE_SYNC_ENDS_ONLY_THE_PLACEMENTS_IT_MADE`.

*Absence is not departure.* Somebody the roster does not mention loses a sync-made placement only
when the source promised a complete list and has been applied before, which is `dry_run`'s pair of
suppressions and for its reasons. Somebody the source says has left loses theirs regardless, which
is the one removal `dry_run` also lets through: the source stating a fact rather than failing to
mention one.

*A department two people claim to lead gets neither*, and a team or a department no registered row
carries is never created: both are named, in `contested` and `unregistered`, and skipped. The sync
reads where people sit; which teams exist is decided in the console.

**Nothing here is scheduled.** No job applies a roster on any install, which is true of the whole
staff sync: `dry_run` is read by the Staff sources screen and nothing applies it. This plan and its
store method are the sync's half of M27.7.4, proved against PostgreSQL, and a caller that runs them
on a schedule is the same missing caller the rest of the roster is waiting for.

Task ids: M27.7.4
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.identity.staff_source import Asserts, Roster, leads_from, teams_from
from brain.tables.organisation import SYNC_ACTOR_PREFIX

#: Why the sync takes away only what it put there.
THE_SYNC_ENDS_ONLY_THE_PLACEMENTS_IT_MADE: Final = (
    "A placement somebody made in the console is a decision a person took, and a source that does "
    "not mention it has not decided anything about it. So the rows the sync may end are the rows "
    "whose actor names this source, and a lead appointed by hand is not replaced by a lead the "
    "source names: the department is reported and left for a person. This is the filter on a "
    "column that brain.identity.staff_sync.THE_SYNC_DELETES_ONLY_WHAT_IT_WROTE calls the weaker "
    "form, for the same reason: these rows share a table with the console's."
)


def sync_actor(source: str) -> str:
    """The actor a placement this source's sync made carries. See `SYNC_ACTOR_PREFIX`."""
    return f"{SYNC_ACTOR_PREFIX}{source}"


@dataclass(frozen=True)
class HeldMembership:
    """One live membership, as the install holds it: the team's path, whose, and who placed them."""

    team: str
    principal_id: str
    added_by: str


@dataclass(frozen=True)
class HeldLead:
    """One live lead, as the install holds it: the department, who, and who appointed them."""

    department: str
    principal_id: str
    appointed_by: str


@dataclass(frozen=True)
class Placement:
    """Somebody the sync would place: a team's path or a department's slug, and whose."""

    where: str
    principal_id: str


@dataclass(frozen=True)
class OrganisationPlan:
    """What one sync would change about teams and leads. Lists of things, never counts."""

    source: str
    to_join: tuple[Placement, ...]
    #: Always rows this source's sync made. Never wider, and never one made in the console.
    to_leave: tuple[HeldMembership, ...]
    to_appoint: tuple[Placement, ...]
    #: Always rows this source's sync made.
    to_stand_down: tuple[HeldLead, ...]
    #: Team paths and department slugs the source names that no registered row carries.
    unregistered: tuple[str, ...]
    #: Departments more than one person is named to lead.
    contested: tuple[str, ...]
    #: Why the plan is narrower than the roster, in words.
    withheld: tuple[str, ...]
    #: Configuration this run refuses to act on. Non-empty means nothing may be applied.
    refusals: tuple[str, ...]

    @property
    def actor(self) -> str:
        return sync_actor(self.source)

    @property
    def safe_to_apply(self) -> bool:
        """False when anything was refused, for `staff_sync.DryRun.safe_to_apply`'s reason."""
        return not self.refusals

    @property
    def changes_nothing(self) -> bool:
        return not (self.to_join or self.to_leave or self.to_appoint or self.to_stand_down)


def organisation_plan(
    roster: Roster,
    *,
    known: Mapping[str, str],
    teams: Collection[str],
    departments: Collection[str],
    memberships: Iterable[HeldMembership] = (),
    leads: Iterable[HeldLead] = (),
    last_applied: datetime | None,
) -> OrganisationPlan:
    """The placements this roster supports, against what the install holds (M27.7.4).

    `known` maps a casefolded work address to the principal already held for it, as `dry_run`
    takes it; an address with no principal is skipped, because provisioning is not this module's.
    `teams` and `departments` are the registered team paths and department slugs.
    `last_applied` is when a sync from this source was last applied, `None` for never.
    """
    actor = sync_actor(roster.source)
    held_memberships = tuple(memberships)
    held_leads = tuple(leads)

    if Asserts.DEPARTMENT not in roster.asserts:
        return OrganisationPlan(
            source=roster.source,
            to_join=(),
            to_leave=(),
            to_appoint=(),
            to_stand_down=(),
            unregistered=(),
            contested=(),
            withheld=(),
            refusals=(
                f"{roster.source!r} is not trusted to say which department somebody is in, so it "
                "cannot say which team they are in or who leads one",
            ),
        )

    withheld: list[str] = []
    if not roster.may_remove():
        withheld.append(
            f"{roster.source!r} did not promise a complete list, so no placement is ended because "
            "somebody is missing from it"
        )
    if last_applied is None:
        withheld.append(
            f"{roster.source!r} has never been applied, so no placement is ended on the strength "
            "of its first run"
        )
    absence_ends = roster.may_remove() and last_applied is not None
    departed = {
        known[one.work_address.casefold()]
        for one in roster.people
        if not one.active and one.work_address.casefold() in known
    }

    unregistered: set[str] = set()
    asserted_teams: set[tuple[str, str]] = set()
    for address, paths in teams_from(roster).items():
        principal = known.get(address)
        if principal is None:
            continue
        for path in paths:
            if path in teams:
                asserted_teams.add((path, principal))
            else:
                unregistered.add(path)

    live_teams = {(one.team, one.principal_id) for one in held_memberships}
    to_join = sorted(asserted_teams - live_teams)
    to_leave = sorted(
        (
            one
            for one in held_memberships
            if one.added_by == actor
            and (one.team, one.principal_id) not in asserted_teams
            and (absence_ends or one.principal_id in departed)
        ),
        key=lambda one: (one.team, one.principal_id),
    )

    contested: list[str] = []
    claimed: dict[str, str] = {}
    for department, addresses in leads_from(roster).items():
        principals = sorted({known[one] for one in addresses if one in known})
        if not principals:
            continue
        if department not in departments:
            unregistered.add(department)
        elif len(principals) > 1:
            contested.append(department)
        else:
            claimed[department] = principals[0]

    held_by_department = {one.department: one for one in held_leads}
    to_appoint: list[Placement] = []
    to_stand_down: list[HeldLead] = []
    for department, principal in sorted(claimed.items()):
        current = held_by_department.get(department)
        if current is not None and current.principal_id == principal:
            continue
        if current is not None and current.appointed_by != actor:
            withheld.append(
                f"{department!r} has a lead appointed in the console, and {roster.source!r} names "
                "somebody else; the sync does not replace a lead a person appointed"
            )
            continue
        if current is not None:
            to_stand_down.append(current)
        to_appoint.append(Placement(where=department, principal_id=principal))
    for current in held_leads:
        if current.appointed_by != actor or current.department in claimed:
            continue
        if current.department in contested:
            continue
        if absence_ends or current.principal_id in departed:
            to_stand_down.append(current)

    return OrganisationPlan(
        source=roster.source,
        to_join=tuple(Placement(where=path, principal_id=who) for path, who in to_join),
        to_leave=tuple(to_leave),
        to_appoint=tuple(to_appoint),
        to_stand_down=tuple(sorted(to_stand_down, key=lambda one: one.department)),
        unregistered=tuple(sorted(unregistered)),
        contested=tuple(sorted(contested)),
        withheld=tuple(withheld),
        refusals=(),
    )
