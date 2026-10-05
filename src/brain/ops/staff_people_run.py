"""The staff sync's people step: every active person on the staff list is a Brain person.

**Until 2026-09-30 the only step that made a Brain person for somebody on the staff list was the
accounts step**, `brain.ops.staff_accounts_run.person_for`, which runs after a sign-in account has
been made or found in the sign-in service. The sync writes `auth.staff_member` rows for everybody
it reads, but People lists principals, and a principal was made only on that path. So on every
install whose accounts client had no key in the vault yet, or no sign-in address, the whole staff
list was read, stored and invisible: measured on the owner's install that day, 123 active rows and
one person on People, and nobody on the list could be placed or granted until they had signed in,
which none of them could. See `A_PERSON_ON_THE_LIST_IS_A_PERSON_BEFORE_THEY_SIGN_IN`.

**This step asks nothing of the sign-in service, so it cannot be stopped by one.** For each active
person on the list whose work address no Brain person is joined to, it makes the person
(`auth.principal`, human, staff or contractor as `employment_of` reads the source's type, in the
department here that answers to the source's, the same as the accounts step made them) and writes
the join: an email binding of the address's digest at `Assurance.UNVERIFIED`, which admits no verb
on any channel. That is the join every later part of the run already follows (the standing step,
the Starter packs, the heads' audit reach, the organisation's placements, the leavers' agents), so
once this has run they reach the whole list rather than the people who happened to sign in.

**It never makes a second person, and sign-in binds to this one.** A person is found by that
email binding before anything is made, whoever made it: the accounts step's `person_for` finds it
the same way and binds the account's sign-in to it, and an administrator linking a sign-in by hand
on the Sign-in links screen binds to the person People already shows. Nothing binds a sign-in by
an address at sign-in time, for `sign_in_binding.AN_ADDRESS_IS_NOT_A_SIGN_IN`'s reason, and this
step does not change that: it makes people, not ways in.

**Only the active are made, and whether anybody may sign in or ask is still the standing step's.**
A leaver, a suspended person or one never activated is not made. A person already made who later
leaves, is suspended or is of a type the install does not allow is kept out by
`brain.identity.standing` on the same run, which disables them and records why, so People shows
them as kept out rather than dropping them. Every active type is made, including one the install
does not allow, because the owner asked that People show each person's type and why they cannot
use the Brain (needs-rupash 115), and a person who does not exist cannot be shown.

**What it does not do.** A person made by hand before the staff list existed, the first
administrator above all, has no email binding, so the list cannot tell that it names them and
this step makes a second person for their address. Duplicates are found by the address's digest
and never by a name, because a name is not an identity and matching on one hands a stranger's row
whatever the named person holds. The two are joined once the hand-made person's work address is
bound to them, by the person themselves at a sign-in the sign-in service vouches for, or by an
administrator on their People page; neither is this step's to guess.

Task ids: M1.10.1
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Update, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.principal import Employment
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.organisation_sync import department_key, sync_actor, sync_trace
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import EmploymentStatus, Roster, StaffRecord
from brain.identity.starter_pack_sync import registered_by_name
from brain.ops.staff_accounts_run import (
    CONTRACTED,
    CONTRACTED_ENGAGEMENT_LASTS,
    NO_REACH,
    PRINCIPAL_PREFIX,
    employment_of,
    engaged_until,
)
from brain.ops.starter_pack_store import registered_departments
from brain.tables.audit import attributed_to
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

#: Why the sync makes a person for everybody active on the list, without the sign-in service.
A_PERSON_ON_THE_LIST_IS_A_PERSON_BEFORE_THEY_SIGN_IN: Final = (
    "People lists Brain persons, and a person was made only when the sign-in service gave the "
    "sync an account for them, so an install whose accounts client was not set up yet read its "
    "whole staff list and showed nobody on it. An active person on the list is a person the "
    "console can see, place and grant before their first sign-in; their sign-in is bound to "
    "that same person later, by the accounts step or by an administrator, and never makes a "
    "second one."
)


def people_to_make(roster: Roster, joined: Iterable[str]) -> tuple[StaffRecord, ...]:
    """The active people on this list whose address no Brain person is joined to, once each.

    `joined` is the digests of the live email bindings. A list cannot name one address twice:
    `Roster` refuses one that does.
    """
    seen = set(joined)
    return tuple(
        person
        for person in roster.people
        if person.standing is EmploymentStatus.ACTIVE and digest_of(person.work_address) not in seen
    )


@dataclass(frozen=True)
class PeopleRun:
    """What the people step came to: how many it made, in a sentence that names nobody."""

    made: int
    #: Contractors still on the list whose end date this run moved on.
    renewed: int = 0

    def sentences(self, *, trial: bool = False) -> tuple[str, ...]:
        if trial:
            return (f"People: {self.made} on the list would be added to People.",)
        said = [f"People: {self.made} on the list added to People."]
        if self.renewed:
            said.append(
                f"People: {self.renewed} contracted on the list kept engaged for another "
                f"{CONTRACTED_ENGAGEMENT_LASTS.days} days."
            )
        return tuple(said)


def still_contracted(roster: Roster) -> tuple[str, ...]:
    """The digests of the active people the list names as contracted, whose end dates move on.

    See `A_CONTRACTOR_ON_THE_LIST_STAYS_ENGAGED_WHILE_LISTED`.
    """
    return tuple(
        sorted(
            {
                digest_of(one.work_address)
                for one in roster.people
                if one.standing is EmploymentStatus.ACTIVE and one.employment_type in CONTRACTED
            }
        )
    )


def renewing(digests: Sequence[str], until: datetime) -> Update:
    """Move on the end date of every contractor joined to one of these addresses, never back."""
    joined = select(PrincipalIdentityRow.principal_id).where(
        PrincipalIdentityRow.channel == Channel.EMAIL.value,
        PrincipalIdentityRow.identity_hash.in_(list(digests)),
        PrincipalIdentityRow.deleted_at.is_(None),
    )
    return (
        update(PrincipalRow)
        .where(
            PrincipalRow.id.in_(joined),
            PrincipalRow.employment == Employment.CONTRACTOR.value,
            PrincipalRow.not_after.is_not(None),
            PrincipalRow.not_after < until,
        )
        .values(not_after=until)
    )


async def _joined(session: AsyncSession, digests: Iterable[str]) -> set[str]:
    wanted = sorted(set(digests))
    if not wanted:
        return set()
    rows = await session.execute(
        select(PrincipalIdentityRow.identity_hash).where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.identity_hash.in_(wanted),
            PrincipalIdentityRow.deleted_at.is_(None),
        )
    )
    return {str(one) for one in rows.scalars()}


async def provide_people(
    sessions: async_sessionmaker[AsyncSession],
    roster: Roster,
    *,
    now: datetime,
    trial: bool = False,
    new_id: Callable[[], str] | None = None,
) -> PeopleRun:
    """Make a Brain person for every active person on the list who has none, in one transaction.

    A trial counts them and writes nothing. Every person and join is attributed to the source's
    sync in the ledger, the way the accounts step's are. `new_id` names each new person and is given
    only by the install check, whose people must be reserved ones; everybody else is `u_` and a
    random hex.
    """
    actor = sync_actor(roster.source)
    async with sessions() as session, session.begin():
        joined = await _joined(session, (digest_of(one.work_address) for one in roster.people))
        making = people_to_make(roster, joined)
        if trial:
            return PeopleRun(made=len(making))
        for statement in attributed_to(
            actor_id=actor, ent_hash=NO_REACH, trace_id=sync_trace("staff-people", now)
        ):
            await session.execute(statement)
        contracted = still_contracted(roster)
        renewed = 0
        if contracted:
            moved = await session.execute(renewing(contracted, now + CONTRACTED_ENGAGEMENT_LASTS))
            renewed = int(getattr(moved, "rowcount", 0) or 0)
        if not making:
            return PeopleRun(made=0, renewed=renewed)
        departments = registered_by_name(
            {
                str(slug): str(name)
                for slug, name in (await session.execute(registered_departments())).all()
            }
        )
        for person in making:
            principal_id = (
                new_id() if new_id is not None else f"{PRINCIPAL_PREFIX}{uuid.uuid4().hex}"
            )
            await session.execute(
                insert(PrincipalRow).values(
                    id=principal_id,
                    kind="human",
                    employment=employment_of(person).value,
                    not_after=engaged_until(person, now),
                    display_name=person.display_name,
                    primary_department=departments.get(department_key(person.department)),
                )
            )
            await session.execute(
                insert(PrincipalIdentityRow).values(
                    channel=Channel.EMAIL.value,
                    identity_hash=digest_of(person.work_address),
                    principal_id=principal_id,
                    bound_at=now,
                    assurance=int(Assurance.UNVERIFIED),
                )
            )
    return PeopleRun(made=len(making), renewed=renewed)
