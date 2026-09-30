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

**A source's spelling is matched to a registered department before anything is compared.** A
directory says `Web Development` and the install's department is the slug `web_development`, so
`slug_of` carries `brain.identity.starter_pack_sync.registered_by_name`'s matching, by slug or name
ignoring case and spacing, into the team paths and the leads. Until 2026-09-29 the plan compared the
source's own spelling with registered slugs, so every department with a space in its name was
`unregistered` and nobody was placed in any of its teams.

**Applied by every scheduled run since 2026-09-29.** This said "nothing here is scheduled" until
the staff sync had run on the owner's install and placed nobody on the Departments and teams screen.
`brain.ops.source_organisation.apply_organisation` is the run's call, after the roster, the heads'
reach and the Starter packs, in a transaction of its own.

**The departments themselves are founded by a person, from what the source names.**
`departments_to_found` turns the names a staff source used into the departments a person is asked to
create, each with the slug it would get, and leaves out every name a registered department already
answers to. The sync never founds one: which departments exist decides which scopes exist, and a
department is the unit every grant is bounded by. See
`A_DEPARTMENT_IS_FOUNDED_BY_A_PERSON_FROM_WHAT_THE_SOURCE_NAMES`.

Task ids: M27.7.4, M1.6.5, M1.6.12
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from brain.core.department import DepartmentError, create_department
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


#: Why the departments a source names are founded from the console and not by the sync.
A_DEPARTMENT_IS_FOUNDED_BY_A_PERSON_FROM_WHAT_THE_SOURCE_NAMES: Final = (
    "A department is the unit every grant, pack and document is bounded by, and founding one "
    "writes the scope it is defined by. A scheduled read that founded whatever a directory named "
    "would let a renamed Lark department become a second department overnight, with its own scope "
    "and nobody in it. So the names a source uses are offered to an administrator as one confirmed "
    "act, each with the slug it would get, and only the ones no registered department already "
    "answers to; the sync then places people in the ones that exist."
)

#: The longest slug a department founded from a source's name is given, well inside the sixty
#: `brain.core.department.Department` allows, so the scopes it starts with fit too.
SLUG_CHARS: Final = 40


def department_key(name: str) -> str:
    """A department's spelling folded for matching: case and runs of spacing ignored.

    The one folding `brain.identity.starter_pack_sync.registered_by_name` and this module both
    use, declared here because `brain.identity.lifecycle` imports this module and not that one.
    """
    return " ".join(name.split()).casefold()


def sync_actor(source: str) -> str:
    """The actor a placement this source's sync made carries. See `SYNC_ACTOR_PREFIX`."""
    return f"{SYNC_ACTOR_PREFIX}{source}"


#: Why a run's trace id is written from the clock without its punctuation.
A_RUN_S_TRACE_IS_ONE_THE_LEDGER_ACCEPTS: Final = (
    "Every audited write a scheduled run makes carries its trace id into obs.audit_entry, whose "
    "trace_id is letters, digits, dot, dash and underscore. An ISO time has a colon and a plus "
    "sign, so a trace built from one is refused by the ledger's check and the whole write with "
    "it; the run's broad catch then logs a class name and every placement is silently lost."
)


def sync_trace(step: str, now: datetime) -> str:
    """The trace id a scheduled run's `step` writes under at `now`, in the ledger's own shape."""
    return f"{step}-{now.astimezone(UTC):%Y%m%dT%H%M%SZ}"


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
    slug_of: Mapping[str, str] | None = None,
) -> OrganisationPlan:
    """The placements this roster supports, against what the install holds (M27.7.4).

    `known` maps a casefolded work address to the principal already held for it, as `dry_run`
    takes it; an address with no principal is skipped, because provisioning is not this module's.
    `teams` and `departments` are the registered team paths and department slugs.
    `last_applied` is when a sync from this source was last applied, `None` for never.
    `slug_of` is `registered_by_name`'s answer, a folded spelling to the registered slug; a
    department it does not answer for is compared as the source spelled it.
    """

    def slug(department: str) -> str:
        return (slug_of or {}).get(department_key(department), department)

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
        for named in paths:
            department, _, team = named.partition(".")
            path = f"{slug(department)}.{team}"
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
    for named, addresses in leads_from(roster).items():
        department = slug(named)
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


# ------------------------------------------------------------- the departments a source names
@dataclass(frozen=True)
class DepartmentToFound:
    """One department a source names that the install has not founded, and the slug it would get."""

    name: str
    slug: str


@dataclass(frozen=True)
class DepartmentsNamed:
    """What founding the departments a source names would do. Names, never a count of people."""

    to_found: tuple[DepartmentToFound, ...]
    #: The source's spellings a registered department already answers to, by slug or name.
    registered: tuple[str, ...]


def _usable(slug: str, name: str) -> bool:
    try:
        create_department("company", slug, name)
    except (DepartmentError, ValueError):
        return False
    return True


def department_slug(name: str) -> str:
    """The slug a department founded from a source's name is given.

    Its letters and digits, lower case, words joined by underscores and cut at `SLUG_CHARS`, so
    `Web Development` is `web_development`. A name with no ASCII letter in it, which is every
    department of a company whose directory is in Chinese, is `department_` and eight characters
    of its digest: a slug is an identifier in every grant, and inventing a transliteration would be
    a guess at a name. A slug the department type refuses is given the digest form too.
    """
    words = re.findall(r"[a-z0-9]+", name.casefold())
    slug = "_".join(words)[:SLUG_CHARS].strip("_")
    if slug and not slug[0].isalpha():
        slug = f"department_{slug}"[:SLUG_CHARS].strip("_")
    if len(slug) < 2 or not _usable(slug, name.strip() or slug):
        digest = hashlib.sha256(department_key(name).encode()).hexdigest()[:8]
        slug = f"department_{digest}"
    return slug


def departments_to_found(
    names: Iterable[str], registered: Mapping[str, str], answers: Mapping[str, str]
) -> DepartmentsNamed:
    """The departments to offer for founding from the names a source used.

    `registered` is every live department's slug to its name, and `answers` is
    `registered_by_name(registered)`. A name a registered department answers to is left out and
    listed, so a second press founds nothing; two spellings of one name are one department; and a
    slug already taken, by a registered department or by an earlier name here, is numbered.
    """
    taken = set(registered)
    seen: set[str] = set()
    to_found: list[DepartmentToFound] = []
    already: list[str] = []
    # By the folded spelling, then the spelling itself, so which of two spellings of one name is
    # shown does not depend on the order a database collation returned them in.
    for raw in sorted(names, key=lambda one: (department_key(one), " ".join(one.split()))):
        name = " ".join(raw.split())
        key = department_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in answers:
            already.append(name)
            continue
        base = department_slug(name)
        slug, at = base, 2
        while slug in taken:
            suffix = f"_{at}"
            slug = f"{base[: SLUG_CHARS - len(suffix)].rstrip('_')}{suffix}"
            at += 1
        taken.add(slug)
        to_found.append(DepartmentToFound(name=name, slug=slug))
    return DepartmentsNamed(to_found=tuple(to_found), registered=tuple(already))
