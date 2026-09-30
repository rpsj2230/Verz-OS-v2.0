"""Which Starter pack each person the staff sync brings in holds, decided without a database.

Needs Rupash item 105 was decided on 2026-09-28: every person the staff sync brings in gets the
Starter pack for their own department automatically, and administrators still add or remove
anything on Govern > Roles. The pack is `brain.identity.lifecycle.STARTER_PACK`, the joiner's
pack, whose capabilities are the knowledge read and its three passage fields, so held over one
department it is exactly the reach that lets a document uploaded for that department answer
that department's people and nobody else. `brain.ops.starter_pack_store` applies what this
returns; this module holds the judgement and no connection, on the split
`brain.identity.staff_sync.audit_reach_for_head` already argues for.

**The sync holds nothing, so what it may give is fixed before it runs.** A person granting a pack
on Govern > Roles is refused any capability they could not grant one at a time, which is
`brain.govern_pack_routes.assign_pack` expanding the pack through `write_grant`. A scheduled run
has no person and no reach to ask that of, so the question is answered by construction instead:
the only pack it writes is the product's joiner pack, the live row is refused if it confers more
than that pack declares, and the only scope it writes is `department_scope` of a registered
department the trusted source places the person in. The grant is attributed to the roster,
`roster.<source>`, which `0003`'s trigger records as the ledger's actor, exactly as the heads'
audit grants are (M1.8.3). See `THE_SYNC_HOLDS_NOTHING_SO_IT_GIVES_ONLY_THE_JOINERS_PACK`.

**Additive, and it ends only what it gave.** A person holding a Starter pack an administrator
assigned keeps it untouched, whatever department the source names: that row is a decision a
person took. A pack the sync gave is retired on exactly the two paths the sync already retires
its own grants on, measured before this was written: a mover, whom the source now places in
another department (`staff_sync.THE_SYNC_DELETES_ONLY_WHAT_IT_WROTE`, as a head's reach is
rewritten on a transfer), and a leaver the run has marked
(`head_audit_store.A_FORMER_HEAD_KEEPS_NOTHING`). Somebody merely absent from the list, or
listed with no department, keeps what they hold. See `THE_SYNC_RETIRES_ONLY_THE_PACKS_IT_GAVE`.

**A department is matched to a registered one, never invented.** A directory says `Finance`
and the install's department is the slug `finance`, so the roster's department is matched,
ignoring case and spacing, to a live department's slug or its name. A department no registered
row carries gives nobody anything and is reported, because a scope over a slug nothing is filed
under is a pack that looks given and reaches nothing.

Rejected: provisioning the pack at sign-in instead. The sign-in path knows who somebody is and
not where they sit, which is the roster's fact; and a pack given once there would never follow
a mover, which is the half of this the owner's decision names.

Task ids: M26.1.2, M26.1.3, M26.2.6
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.department import department_scope
from brain.core.scope import Scope
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.organisation_sync import department_key
from brain.identity.packs import PackAssignment
from brain.identity.staff_source import Asserts, Roster
from brain.identity.staff_sync import GRANTED_BY_CHARS, ROSTER_PREFIX
from brain.identity.teams import PrincipalSubject

# ------------------------------------------------------------------ written-down reasons
#: Why a run with no person behind it may give anybody anything.
THE_SYNC_HOLDS_NOTHING_SO_IT_GIVES_ONLY_THE_JOINERS_PACK: Final = (
    "Nobody grants what they do not hold, and a scheduled run holds nothing. So what the sync "
    "gives was decided before it ran: the owner decided every synced person gets the Starter "
    "pack for their own department (needs-rupash 105), the product declares that pack as "
    "brain.identity.lifecycle.STARTER_PACK, and the only scope written is the department a "
    "source trusted with departments places the person in. The live pack row is refused if it "
    "confers anything that declaration does not, because an edited pack is what would make a "
    "nightly run hand out a capability nobody decided. The grant names the roster as its "
    "granter, which the ledger records as the actor, as for the heads' audit grants."
)

#: Why the sync ends a pack it gave and never one a person gave.
THE_SYNC_RETIRES_ONLY_THE_PACKS_IT_GAVE: Final = (
    "Revocation is the deletion of a grant, and a pack an administrator assigned is a decision "
    "a person took, so the sync neither replaces nor retires one whatever the source says. A "
    "pack the sync gave is retired on the two paths it already retires its own grants on: a "
    "mover the source now places in another department, whose old department's pack is "
    "retired as the new one is given, and a leaver the run marked. Absence from the list, and a "
    "person listed with no department, retire nothing: an export that half answered and a "
    "department lookup that failed look exactly like those."
)

#: Why a department nobody registered gives nobody anything.
A_DEPARTMENT_NOBODY_REGISTERED_GIVES_NOTHING: Final = (
    "A document is filed under a registered department's slug, so a pack scoped to a department "
    "no registered row carries matches no passage and reads, on every screen that lists it, as "
    "reach somebody was given. The sync reads where people sit and never decides which "
    "departments exist, so the name is reported and nobody is given a pack over it."
)

#: Why a synced Starter pack carries no lapse, unlike a head's audit grant.
A_STARTER_PACK_DOES_NOT_LAPSE_WITH_THE_SYNC: Final = (
    "A head's audit grant lapses two sync intervals after its reading, so a stopped sync closes "
    "a reach over other people. The Starter pack is a person's reach over their own department's "
    "documents, and a lapse would turn one broken credential into everybody's answers going "
    "empty at once. Departure is covered without it: the leaver path retires the pack and the "
    "identity provider refuses the sign-in."
)

#: What an administrator's removal of a synced pack amounts to, stated rather than hidden.
A_REMOVED_SYNCED_PACK_IS_GIVEN_AGAIN_ON_THE_NEXT_RUN: Final = (
    "The application cannot read a retired assignment, so the next run cannot tell a pack an "
    "administrator removed from one never given, and gives it again while the source still "
    "places the person in that department. An administrator who wants somebody to keep a "
    "different reach assigns the Starter pack themselves, which the sync never touches."
)

#: The reason written on every pack the sync gives.
REASON: Final = "the staff list from {source} places them in {department}"


@dataclass(frozen=True)
class HeldStarter:
    """One live Starter pack assignment, as the install holds it."""

    principal_id: str
    scope: Scope
    granted_by: str

    @property
    def given_by_a_sync(self) -> bool:
        """True when a staff sync wrote this row. See `THE_SYNC_RETIRES_ONLY_THE_PACKS_IT_GAVE`."""
        return self.granted_by.startswith(ROSTER_PREFIX)


@dataclass(frozen=True)
class StarterPlan:
    """What one run gives and retires. Lists rather than counts, for `DryRun`'s reason."""

    source: str
    #: New assignments, each the Starter pack over one registered department.
    to_assign: tuple[PackAssignment, ...]
    #: Assignments a sync gave that this run ends: a mover's old department, or a leaver's.
    to_retire: tuple[HeldStarter, ...]
    #: Department names the source used that no registered department carries.
    unregistered: tuple[str, ...]
    #: Why the plan does less than the roster asks, in words, naming no person.
    withheld: tuple[str, ...]
    #: Configuration this run refuses to act on. Non-empty means nothing may be applied.
    refusals: tuple[str, ...]

    @property
    def safe_to_apply(self) -> bool:
        """False when anything was refused."""
        return not self.refusals

    @property
    def changes_nothing(self) -> bool:
        """True when every person already holds what this roster says they should."""
        return not (self.to_assign or self.to_retire)


def department_of(scope: Scope) -> str | None:
    """The department a scope is exactly, or None when it is anything else."""
    if len(scope.clauses) != 1 or not isinstance(scope.clauses[0].value, str):
        return None
    named = scope.clauses[0].value
    return named if department_scope(named) == scope else None


_key = department_key


def registered_by_name(departments: Mapping[str, str]) -> dict[str, str]:
    """A roster's spelling to the registered slug, by slug or by name, ignoring case and spacing.

    A spelling two departments could both answer to is dropped rather than resolved: guessing
    which department bounds somebody's reach is guessing at their reach.
    """
    found: dict[str, set[str]] = {}
    for slug, name in departments.items():
        for spelling in {_key(slug), _key(name)}:
            found.setdefault(spelling, set()).add(slug)
    return {spelling: next(iter(slugs)) for spelling, slugs in found.items() if len(slugs) == 1}


def starter_plan(
    roster: Roster,
    *,
    known: Mapping[str, str],
    standing: Collection[str],
    departments: Mapping[str, str],
    held: Iterable[HeldStarter],
    leavers: Collection[str],
    pack: Collection[str] | None,
    read_at: datetime,
) -> StarterPlan:
    """The Starter packs this roster gives and retires, against what the install holds.

    `known` maps a casefolded work address to the principal an email binding proves, as
    `audit_reach_for_head` takes it; somebody nobody has bound is given nothing yet and is given
    their pack on the first run after they are. `standing` is the principals who may hold a
    standing entitlement at all: a partner holds none and a service is not a person, which is
    `lifecycle.provision`'s refusal of both. `departments` is every live department's slug to
    its name, `held` every live Starter assignment, `leavers` the principals the roster has
    marked as having left, and `pack` the capabilities the live Starter row holds, None when
    there is none.
    """
    granted_by = f"{ROSTER_PREFIX}{roster.source}"
    refusals: list[str] = []
    if Asserts.DEPARTMENT not in roster.asserts:
        refusals.append(
            f"{roster.source!r} is not trusted to say which department somebody is in, so it "
            "cannot say which department's Starter pack they hold"
        )
    declared = {one.value for one in STARTER_PACK.capabilities}
    if pack is None:
        refusals.append(
            f"there is no live {STARTER_PACK.slug!r} pack, so there is nothing to give; the "
            "install was never furnished or an administrator retired it"
        )
    elif not set(pack) <= declared:
        refusals.append(
            f"the live {STARTER_PACK.slug!r} pack confers more than the joiner's pack declares. "
            + THE_SYNC_HOLDS_NOTHING_SO_IT_GIVES_ONLY_THE_JOINERS_PACK
        )
    if len(granted_by) > GRANTED_BY_CHARS:
        refusals.append(
            f"source {roster.source!r} is too long to record as a granter; the column holds "
            f"{GRANTED_BY_CHARS} characters"
        )
    if refusals:
        return StarterPlan(
            source=roster.source,
            to_assign=(),
            to_retire=(),
            unregistered=(),
            withheld=(),
            refusals=tuple(refusals),
        )

    registered = registered_by_name(departments)
    placed: dict[str, set[str]] = {}
    for person in roster.people:
        principal = known.get(person.work_address.casefold())
        if person.active and principal is not None and _key(person.department):
            placed.setdefault(principal, set()).add(person.department.strip())

    held_by = {one.principal_id: one for one in held}
    to_assign: list[PackAssignment] = []
    to_retire: list[HeldStarter] = []
    unregistered: set[str] = set()
    withheld: set[str] = set()
    for principal, named in sorted(placed.items()):
        if principal not in standing:
            continue
        if len({_key(one) for one in named}) > 1:
            withheld.add(
                "somebody is listed in more than one department, so neither department's pack "
                "is given to them until the list agrees with itself"
            )
            continue
        department = min(named)
        slug = registered.get(_key(department))
        current = held_by.get(principal)
        if current is not None and not current.given_by_a_sync:
            withheld.add(
                "a Starter pack an administrator assigned is left as it is, whatever department "
                "the list names"
            )
            continue
        if current is not None and slug is not None and department_of(current.scope) == slug:
            continue
        if current is not None:
            # A mover: the source places them somewhere else, so the pack the sync gave for
            # the old department ends as the new one is given.
            to_retire.append(current)
        if slug is None:
            unregistered.add(department)
            continue
        to_assign.append(
            PackAssignment(
                subject=PrincipalSubject(principal_id=principal),
                pack_slug=STARTER_PACK.slug,
                scope=department_scope(slug),
                granted_by=granted_by,
                reason=REASON.format(source=roster.source, department=slug),
                granted_at=read_at,
            )
        )

    to_retire.extend(
        one
        for one in sorted(held_by.values(), key=lambda one: one.principal_id)
        if one.given_by_a_sync and one.principal_id in leavers and one.principal_id not in placed
    )
    if unregistered:
        withheld.add(A_DEPARTMENT_NOBODY_REGISTERED_GIVES_NOTHING)
    return StarterPlan(
        source=roster.source,
        to_assign=tuple(to_assign),
        to_retire=tuple(to_retire),
        unregistered=tuple(sorted(unregistered)),
        withheld=tuple(sorted(withheld)),
        refusals=(),
    )
