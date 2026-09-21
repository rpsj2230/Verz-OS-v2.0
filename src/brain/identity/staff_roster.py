"""What one scheduled read of the staff list writes, decided without a database.

`brain.identity.staff_sync.dry_run` says what a roster would change and writes nothing, and
`brain.identity.staff_address.address_changes` says what a changed address means and rebinds
nothing. Both said plainly that nothing applied them. This is the pure half of applying them: it
takes the roster the source answered with, the members the last applied run left behind and when
that run was, and returns the rows to write and the run record to append. `brain.ops.staff_sync_run`
holds the connection and no judgement.

**The plan written is the plan `dry_run` computed, from the same call.** Every addition and every
leaver below comes out of one `DryRun`, so the first-run rule, the completeness rule and a source
that says somebody left are decided in exactly one place, and the run record carries the same
lists the console trial would have shown. A second set difference here would be a second answer to
what a sync proposes. See `THE_RUN_WRITES_THE_DRY_RUN_AND_NOTHING_ELSE`.

**The roster keeps a digest of each address and never the address.** A stored member is keyed in
`known` by its address when this run's roster names that address and by its digest otherwise, and
the two can never collide because a digest has no `@`. So `dry_run` sees every current person by
address and every absent one as a key it cannot name, which is all it needs to say who is absent.
See `THE_ROSTER_KEEPS_A_DIGEST`.

**Roles are not applied, and that is item 39's answer rather than an omission.** The staff list
lists people and roles are set in the console, so the rules handed to `dry_run` are always empty
and nothing here writes `auth.directory_role_grant`. A source's trust still decides what is kept:
a department is stored only when `departments_from` answers for the source.

**A leaver is marked and nothing is revoked.** See `A_LEAVER_IS_MARKED_AND_NOTHING_IS_REVOKED`.

Rejected: provisioning a principal for each person added. `assertions_from` already refuses to
invent one, `brain.identity.lifecycle.provision` owns that decision, and `brain.identity.
sign_in_binding` is why a roster row is never a sign-in: a spreadsheet can name somebody and the
person is still refused until an administrator binds a Keycloak subject (M1.6.2).

Task ids: M1.6.1, M1.6.2, M1.6.3, M1.6.7, M1.6.8, M1.6.12
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.identity.staff_address import address_changes
from brain.identity.staff_source import Roster, departments_from
from brain.identity.staff_sync import DryRun, dry_run

# ------------------------------------------------------------------ written-down reasons
#: Why the run applies the dry run's own lists.
THE_RUN_WRITES_THE_DRY_RUN_AND_NOTHING_ELSE: Final = (
    "A dry run assembled by a different code path is a rehearsal of a different performance. "
    "The scheduled run calls dry_run with the inputs it holds and writes exactly the people that "
    "plan names, so the first-run rule and the completeness rule are decided once, and what the "
    "screen shows a run did is what the plan said it would do."
)

#: Why the address is not a column.
THE_ROSTER_KEEPS_A_DIGEST: Final = (
    "A table of work addresses joined to names and departments is the company's phone book, which "
    "auth.principal_identity refuses to be. The roster keeps the digest principal_identity keeps "
    "for an email binding, so a member joins to a principal by one equality, and the address is "
    "read from the source on each run and written nowhere."
)

#: Why marking somebody as having left revokes nothing.
A_LEAVER_IS_MARKED_AND_NOTHING_IS_REVOKED: Final = (
    "Entitlements are additive and revocation is the deletion of a grant somebody decided. A "
    "scheduled read that deleted grants would turn a filter somebody narrowed into a mass "
    "revocation nobody approved, so a leaver is marked with the reason, their agents are listed "
    "for a new owner, and the offboarding that removes access is a person's act on the console."
)

#: What a run says when a changed address was somebody else's. Carries no address and no name.
AN_ADDRESS_CHANGED_HANDS: Final = (
    "An address in this list belonged to a different person on the last run. Nothing was changed "
    "for it: moving it would hand one person's roster entry to another, so a person has to look."
)


class RunOutcome(enum.StrEnum):
    """What one scheduled attempt came to. Mirrored by `brain.tables.staff.RUN_OUTCOMES`."""

    #: The plan changed somebody and was written.
    APPLIED = "applied"
    #: The plan changed nobody. Recorded, because it is also the run `last_applied` is read from.
    UNCHANGED = "unchanged"
    #: The source, its setting or the roster it answered with was refused. Nobody changed.
    MISCONFIGURED = "misconfigured"
    #: No credential is held for the staff source, or there is no vault. Nobody changed.
    NO_CREDENTIAL = "no_credential"
    #: The source refused the credential it was given. Nobody changed.
    CREDENTIAL_REFUSED = "credential_refused"
    #: The source or the vault did not answer. Nobody changed.
    UNREACHABLE = "unreachable"
    #: This kind of source has no scheduled reader. Nobody changed.
    NOT_SCHEDULABLE = "not_schedulable"


#: The outcomes after which a sync counts as applied, for `last_applied`.
APPLIED_OUTCOMES: Final[frozenset[RunOutcome]] = frozenset(
    {RunOutcome.APPLIED, RunOutcome.UNCHANGED}
)


class LeftBecause(enum.StrEnum):
    """Why a member was marked as having left. Mirrored by `brain.tables.staff.LEFT_BECAUSE`."""

    #: The source said so, which survives an incomplete roster and a first run.
    SOURCE_SAYS_LEFT = "source_says_left"
    #: A complete roster, on a run after the first, no longer named them.
    ABSENT_FROM_COMPLETE_ROSTER = "absent_from_complete_roster"


@dataclass(frozen=True)
class StoredMember:
    """One `auth.staff_member` row as the run reads it."""

    address_hash: str
    display_name: str
    stable_id: str | None = None
    left_at: datetime | None = None


class Write(enum.StrEnum):
    """What happens to one member row."""

    #: A new row, or a row whose person had left and is listed again.
    ADD = "add"
    #: Still listed: name, department, identifier and the last time they were listed.
    REFRESH = "refresh"
    #: The row moves to a new address digest under the identifier the source issues.
    RENAME = "rename"
    #: Marked as having left, with the reason.
    MARK_LEFT = "mark_left"


@dataclass(frozen=True)
class MemberWrite:
    """One row to write. `was_hash` is set on a rename and names the row being moved."""

    write: Write
    address_hash: str
    display_name: str
    department: str | None = None
    stable_id: str | None = None
    left_because: LeftBecause | None = None
    was_hash: str | None = None


@dataclass(frozen=True)
class Application:
    """What one run writes: the member rows, and the lists its run record carries."""

    source: str
    plan: DryRun
    writes: tuple[MemberWrite, ...]
    added: tuple[str, ...]
    marked_left: tuple[str, ...]
    renamed: tuple[str, ...]
    withheld: tuple[str, ...]

    @property
    def outcome(self) -> RunOutcome:
        """Applied when anybody changed, unchanged otherwise. A refresh changes nobody."""
        changing = {Write.ADD, Write.RENAME, Write.MARK_LEFT}
        return (
            RunOutcome.APPLIED
            if any(one.write in changing for one in self.writes)
            else RunOutcome.UNCHANGED
        )


def digest_of(address: str) -> str:
    """The digest a member is kept under, which is an email binding's own. See the module note."""
    return identity_hash(Channel.EMAIL, address)


def application_for(
    roster: Roster,
    *,
    stable_ids: Mapping[str, str],
    aliases: Mapping[str, Sequence[str]],
    members: Sequence[StoredMember],
    last_applied: datetime | None,
) -> Application:
    """The rows one run writes, from the plan `dry_run` makes of this roster and these members.

    Refuses nothing itself: a plan `dry_run` marks unsafe is the caller's to refuse before this
    is asked, and `brain.ops.staff_sync_run` records it as misconfigured and writes no row. The
    rename step runs `address_changes` over the same keys `dry_run` saw, so a move under a stable
    identifier is a rename rather than a leaver and a joiner, and an address that changed hands
    is written for nobody.
    """
    listed = {one.work_address.casefold(): one for one in roster.people}
    by_digest = {digest_of(address): address for address in listed}
    live = [one for one in members if one.left_at is None]
    left = {one.address_hash for one in members if one.left_at is not None}

    def key(member: StoredMember) -> str:
        return by_digest.get(member.address_hash, member.address_hash)

    known = {key(one): one.address_hash for one in live}
    plan = dry_run(roster, known=known, last_applied=last_applied)

    reading = address_changes(
        roster=roster,
        previous={key(one): one.stable_id for one in live if one.stable_id},
        current={address.casefold(): ident for address, ident in stable_ids.items()},
        retained=aliases,
    )
    moved = {change.now: change for change in reading.renamed}
    moved_from = {change.was for change in reading.renamed}
    disputed = {one.address for one in reading.reissued}

    departments = departments_from(roster)
    names = {one.address_hash: one.display_name for one in members}
    writes: list[MemberWrite] = []
    added: list[str] = []
    renamed: list[str] = []

    for person in plan.would_add:
        address = person.work_address.casefold()
        change = moved.get(address)
        if change is not None:
            writes.append(
                MemberWrite(
                    write=Write.RENAME,
                    address_hash=digest_of(address),
                    display_name=person.display_name,
                    department=departments.get(address) or None,
                    stable_id=change.stable_id,
                    was_hash=change.was if change.was not in listed else digest_of(change.was),
                )
            )
            renamed.append(person.display_name)
            continue
        writes.append(
            MemberWrite(
                write=Write.ADD,
                address_hash=digest_of(address),
                display_name=person.display_name,
                department=departments.get(address) or None,
                stable_id=stable_ids.get(address),
            )
        )
        added.append(person.display_name)

    for address, person in sorted(listed.items()):
        if address not in known or not person.active or address in disputed:
            continue
        writes.append(
            MemberWrite(
                write=Write.REFRESH,
                address_hash=digest_of(address),
                display_name=person.display_name,
                department=departments.get(address) or None,
                stable_id=stable_ids.get(address),
            )
        )

    marked: list[str] = []
    leaving = [(one, LeftBecause.SOURCE_SAYS_LEFT) for one in plan.would_deactivate] + [
        (one, LeftBecause.ABSENT_FROM_COMPLETE_ROSTER)
        for one in plan.would_remove
        if one not in moved_from
    ]
    for gone, why in leaving:
        digest = known[gone]
        if digest in left:
            continue
        name = listed[gone].display_name if gone in listed else names[digest]
        writes.append(
            MemberWrite(
                write=Write.MARK_LEFT, address_hash=digest, display_name=name, left_because=why
            )
        )
        marked.append(name)

    withheld = list(plan.withheld)
    if reading.reissued:
        withheld.append(AN_ADDRESS_CHANGED_HANDS)
    return Application(
        source=roster.source,
        plan=plan,
        writes=tuple(writes),
        added=tuple(added),
        marked_left=tuple(marked),
        renamed=tuple(renamed),
        withheld=tuple(withheld),
    )
