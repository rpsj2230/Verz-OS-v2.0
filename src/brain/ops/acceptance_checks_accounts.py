"""The install acceptance check for the staff sync's sign-in accounts, with nothing made or sent.

The owner decided on 2026-09-29 (needs-rupash 115) that the staff sync gives each active person a
Brain account and sends nobody anything. On an install that is two halves, and this check can only
honestly do one of them. **The install's half is the plan and the Brain side**: who is given an
account, who is linked, whose account is closed, and the Brain person, sign-in binding, member grant
and roster join each account comes with, written through the same functions the nightly run uses,
against the install's own schema, as the application role, in the harness's transaction, which is
always rolled back. **The sign-in service's half is not done here and the sentence says so**: this
check never calls Keycloak, so no account is made or closed there and no email can be sent. That
half is proved against a stand-in Keycloak in `tests/unit/test_sign_in_accounts.py` and
`tests/unit/test_staff_accounts_run.py`, including that nothing is ever sent.

**The accounts are a stand-in list and the people are reserved.** The staff source is named
`acceptance`, which no install chooses; the addresses are made up on a domain nothing delivers to;
every principal is a reserved one, found through a roster join the check writes, so no person is
made; and the account identifiers are the run's own and name no account on any sign-in service.

**The second check is the standing step (package 2 of item 115)**: reserved people joined to the
list, one suspended, one of a type not allowed, one an administrator disabled, and one working; it
shows who cannot sign in or ask, through the same live-principal read the gate makes, and who is let
back in and who is not.

Rejected: calling the install's Keycloak with the release's accounts client and a reserved person,
which would make a real account on the owner's sign-in service, and a real reset email if anybody
pressed Forgot password for it. The coordinator's rule for this check was that it must not.

**The third check is Forgot password's mail (M40.7.1)**: the host the sign-in service reported,
when the release last gave it the relay, against the relay saved on Notifications. The report is the
release's, read inside Keycloak's container by its own administrator, because nothing in the
application may read a realm's settings (`brain.ops.sign_in_mail`); the password is never compared
or read, and Keycloak shows it masked anyway.

**The fourth check is the people step (2026-09-30)**: a staff list naming one reserved person
already joined, one new active person and one leaver, read by `provide_people` exactly as the
nightly run reads it, makes one person, who is then on the directory's own read of People and
joined to their row by their address's digest, and a second read makes nobody. The person it makes
is named as a reserved principal through `new_id`, so nothing outside the harness's rolled-back
transaction ever holds them.

Task ids: M38.5.1, M1.6.16, M1.6.17, M1.6.14, M1.6.15, M40.7.1, M1.10.3, M1.6.20, M1.6.21
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import insert, select

from brain.directory_routes import live_people
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.departments_from import as_the_console_places_them
from brain.identity.organisation_store import moving_people
from brain.identity.organisation_sync import sync_actor
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.principal_state_store import StoredPrincipalStates
from brain.identity.principal_store import StoredPrincipals
from brain.identity.staff_accounts import (
    DEFAULT_ALLOWED,
    AccountRefusal,
    HeldAccount,
    account_plan,
)
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)
from brain.identity.standing import standings
from brain.install import InstallError, value_of
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import Harness
from brain.ops.staff_accounts_run import person_for
from brain.ops.staff_people_run import provide_people
from brain.ops.standing_run import apply_standing, plan_standing
from brain.tables.audit import AuditEntryRow
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 230

#: The staff source the check lists people from. No install chooses a source by this name.
SOURCE = "acceptance"

#: The check's refusal when the process running it has no sign-in address.
NO_ISSUER_HERE = "the worker is not given this install's sign-in address, so no account is made"

#: Why the mail check is not run on an install with no relay saved.
NO_RELAY_FOR_THE_RESET_EMAIL: Final = (
    "no mail relay is saved on Notifications, so the sign-in service is given none and its own "
    "email settings are left as they are"
)

#: Why the mail check is not run before a release has given the realm the relay.
NOT_GIVEN_TO_THE_SIGN_IN_SERVICE_YET: Final = (
    "no release has given the sign-in service this install's relay yet; the release does after "
    "its next deploy, and a sign-in service that is not beside the application sets its own"
)


def _address(h: Harness, principal_id: str) -> str:
    return f"{principal_id.replace('.', '-')}-{h.run}@acceptance.invalid"


def _account(h: Harness, principal_id: str, *, made: bool = False) -> HeldAccount:
    """A stand-in account for a reserved principal: the run's own identifier, no service's."""
    address = _address(h, principal_id)
    return HeldAccount(
        account_id=f"acceptance-{h.run}-{principal_id.rsplit('.', 2)[-2]}-{principal_id[-3:]}",
        email=address,
        enabled=True,
        source=SOURCE if made else "",
        stable_id=address if made else "",
        made_by_sync=made,
    )


async def _joined(h: Harness, principal_id: str) -> None:
    """The roster's join, as the accounts step leaves it: an email binding that admits nothing."""
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            channel=Channel.EMAIL.value,
            identity_hash=digest_of(_address(h, principal_id)),
            principal_id=principal_id,
            bound_at=h.now,
            assurance=int(Assurance.UNVERIFIED),
        ),
    )


async def _signs_in_as(h: Harness, issuer: str, account: HeldAccount) -> Any:
    found = await h.execute(
        select(PrincipalIdentityRow.principal_id).where(
            PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
            PrincipalIdentityRow.identity_hash == subject_digest(issuer, account.account_id),
            PrincipalIdentityRow.deleted_at.is_(None),
        )
    )
    return found.scalar_one_or_none()


async def _disabled(h: Harness, principal_id: str) -> bool:
    found = await h.execute(select(PrincipalRow.disabled_at).where(PrincipalRow.id == principal_id))
    return found.scalar_one() is not None


@check(
    leaves=("M1.6.16", "M1.6.17"),
    sentence=(
        "On reserved people and stand-in accounts: an active person is given an account bound to "
        "their Brain person, one a person made is linked and kept, a leaver's is closed and their "
        "Brain person disabled, an outsourced person gets none. It calls no sign-in service and "
        "sends nothing; making and closing accounts there, and that nobody is emailed, are proved "
        "on a stand-in Keycloak in the unit tests."
    ),
)
async def the_staff_sync_gives_the_active_an_account_and_closes_a_leaver_s(h: Harness) -> None:
    try:
        issuer = value_of("INSTALL_OIDC_ISSUER")
    except InstallError as unset:
        raise CheckFailedError(NO_ISSUER_HERE) from unset
    first, second = RESERVED_DEPARTMENTS
    joiner, by_hand = h.principal(first, "one"), h.principal(first, "two")
    leaver, outsourced = h.principal(second, "one"), h.principal(second, "two")
    for pid, department in (
        (joiner, first),
        (by_hand, first),
        (leaver, second),
        (outsourced, second),
    ):
        await h.person(pid, department=department)
        await _joined(h, pid)

    def listed(pid: str, **kind: Any) -> StaffRecord:
        status = kind.get("status", EmploymentStatus.ACTIVE)
        return StaffRecord(
            _address(h, pid),
            "Acceptance check",
            active=status is EmploymentStatus.ACTIVE,
            status=status,
            employment_type=kind.get("employment_type", EmploymentType.REGULAR),
        )

    roster = Roster(
        source=SOURCE,
        complete=True,
        # A directory's trust, as the plan requires before it gives anybody an account.
        asserts=DEFAULT_TRUST["lark"],
        people=(
            listed(joiner),
            listed(by_hand),
            listed(leaver, status=EmploymentStatus.LEFT),
            listed(outsourced, employment_type=EmploymentType.OUTSOURCED),
        ),
    )
    held = (_account(h, by_hand), _account(h, leaver, made=True))
    plan = account_plan(
        roster, stable_ids={}, accounts=held, allowed=DEFAULT_ALLOWED, absent_is_gone=True
    )
    if [one.person.work_address for one in plan.to_make] != [_address(h, joiner)]:
        raise CheckFailedError("the active person was not the one given an account")
    if [one.account.account_id for one in plan.to_link] != [held[0].account_id]:
        raise CheckFailedError("the account a person made was not linked")
    if [one.account_id for one in plan.to_disable] != [held[1].account_id]:
        raise CheckFailedError("the leaver's account was not the one closed")
    if plan.refused != {AccountRefusal.NOT_ACTIVE: 1, AccountRefusal.TYPE_NOT_ALLOWED: 1}:
        raise CheckFailedError("a leaver or an outsourced person was planned an account")

    actor = sync_actor(SOURCE)
    made = _account(h, joiner)
    # What the run does after the sign-in service answers: the person behind each account.
    for account, person in (
        (made, roster.people[0]),
        (held[0], roster.people[1]),
        (held[1], roster.people[2]),
    ):
        found = await person_for(
            h.sessions,
            account=account,
            person=person,
            issuer=issuer,
            actor=actor,
            now=h.now,
            trace_id=h.trace_id,
        )
        if found != await _signs_in_as(h, issuer, account):
            raise CheckFailedError("an account was not bound to the Brain person the roster joins")
    if await _signs_in_as(h, issuer, made) != joiner:
        raise CheckFailedError("the new account signs in as somebody other than the joiner")

    # The standing step the run applies after the accounts step: the leaver and the outsourced
    # person kept out, the two still working let alone.
    where = standings(members=(), writes=(), people=roster.people)
    kept = await plan_standing(
        h.sessions, source=SOURCE, standings=where, allowed=DEFAULT_ALLOWED, now=h.now
    )
    await apply_standing(h.sessions, kept, source=SOURCE, now=h.now)
    if not await _disabled(h, leaver):
        raise CheckFailedError("the leaver's Brain person was not disabled")
    if await _disabled(h, joiner) or await _disabled(h, by_hand):
        raise CheckFailedError("a person who had not left was disabled")
    strangers = await h.execute(
        select(PrincipalIdentityRow.principal_id).where(
            PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
            PrincipalIdentityRow.identity_hash.in_(
                [subject_digest(issuer, one.account_id) for one in (made, *held)]
            ),
            ~PrincipalIdentityRow.principal_id.startswith(f"acceptance.{h.run}."),
        )
    )
    if strangers.first() is not None:
        raise CheckFailedError("an account was bound to a person the check did not make")


@check(
    leaves=("M1.6.14", "M1.6.15"),
    sentence=(
        "On reserved people joined to a staff list: one it says is suspended and one of a type the "
        "install does not allow cannot sign in or ask; when it lists the first as active again "
        "they can; one an administrator disabled stays disabled whatever the list says; and "
        "somebody the list says is working is never touched."
    ),
)
async def the_staff_list_keeps_out_whom_it_names_and_lets_back_its_own(
    h: Harness,
) -> None:
    first, second = RESERVED_DEPARTMENTS
    suspended, working = h.principal(first, "one"), h.principal(first, "two")
    outsourced, by_hand = h.principal(second, "one"), h.principal(second, "two")
    for pid, department in (
        (suspended, first),
        (working, first),
        (outsourced, second),
        (by_hand, second),
    ):
        await h.person(pid, department=department)
        await _joined(h, pid)
    await StoredPrincipalStates(h.sessions).set_disabled(
        by_hand,
        disabled=True,
        may=lambda _department: True,
        by=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )

    def listed(pid: str, status: EmploymentStatus, kind: EmploymentType) -> StaffRecord:
        return StaffRecord(
            _address(h, pid),
            "Acceptance check",
            active=status is EmploymentStatus.ACTIVE,
            status=status,
            employment_type=kind,
        )

    active, regular = EmploymentStatus.ACTIVE, EmploymentType.REGULAR
    before = (
        listed(suspended, EmploymentStatus.SUSPENDED, regular),
        listed(working, active, regular),
        listed(outsourced, active, EmploymentType.OUTSOURCED),
        listed(by_hand, active, regular),
    )
    once = await plan_standing(
        h.sessions,
        source=SOURCE,
        standings=standings(members=(), writes=(), people=before),
        allowed=DEFAULT_ALLOWED,
        now=h.now,
    )
    await apply_standing(h.sessions, once, source=SOURCE, now=h.now)
    principals = StoredPrincipals(h.sessions)
    if await principals.live_principal(suspended) is not None:
        raise CheckFailedError("somebody the list says is suspended can still sign in and ask")
    if await principals.live_principal(outsourced) is not None:
        raise CheckFailedError("somebody of a type the install does not allow can still ask")
    if await principals.live_principal(working) is None:
        raise CheckFailedError("somebody the list says is working was kept out")

    after = (listed(suspended, active, regular), *before[1:])
    again = await plan_standing(
        h.sessions,
        source=SOURCE,
        standings=standings(members=(), writes=(), people=after),
        allowed=DEFAULT_ALLOWED,
        now=h.now,
    )
    await apply_standing(h.sessions, again, source=SOURCE, now=h.now)
    if await principals.live_principal(suspended) is None:
        raise CheckFailedError("somebody the list lets back in is still kept out")
    if await principals.live_principal(by_hand) is not None:
        raise CheckFailedError("the list let back in somebody an administrator had disabled")


@check(
    leaves=("M40.7.1",),
    sentence=(
        "The sign-in service sends Forgot password through the mail relay saved on "
        "Notifications: the host it reported, when the release last gave it the relay, is the "
        "relay's host. The password is never read or compared."
    ),
)
async def forgot_password_is_sent_through_the_relay_on_notifications(h: Harness) -> None:
    from brain.ops.mail import settings_from_rows, settings_rows
    from brain.ops.sign_in_mail import mirrored_of

    async with h.sessions() as session:
        relay = settings_from_rows(await settings_rows(session))
        mirrored = await mirrored_of(session)
    if relay is None:
        raise CheckNotRunError(NO_RELAY_FOR_THE_RESET_EMAIL)
    if mirrored is None:
        raise CheckNotRunError(NOT_GIVEN_TO_THE_SIGN_IN_SERVICE_YET)
    if mirrored.host != relay.host:
        raise CheckFailedError(
            "the sign-in service reported a mail host that is not the relay saved on Notifications"
        )


@check(
    leaves=("M1.10.1", "M1.10.3"),
    sentence=(
        "On a reserved staff list: an active person nobody is joined to is made a person, on "
        "People and joined to their row, one already joined is not made again, a leaver is not "
        "made, and a second read makes nobody. It calls no sign-in service and sends nothing; the "
        "person is reserved and rolled back with the check."
    ),
)
async def the_staff_list_puts_every_active_person_on_people(
    h: Harness,
) -> None:
    first, _second = RESERVED_DEPARTMENTS
    known = h.principal(first, "one")
    await h.person(known, department=first)
    await _joined(h, known)
    newcomer, leaver = h.principal(first, "made"), h.principal(first, "left")
    roster = Roster(
        source=SOURCE,
        complete=True,
        asserts=DEFAULT_TRUST["lark"],
        people=(
            StaffRecord(_address(h, known), "Acceptance check one"),
            StaffRecord(_address(h, newcomer), "Acceptance check made", department=first),
            StaffRecord(_address(h, leaver), "Acceptance check left", active=False),
        ),
    )
    made = await provide_people(h.sessions, roster, now=h.now, new_id=lambda: newcomer)
    if made.made != 1:
        raise CheckFailedError("the staff list did not make exactly the one new active person")
    listed = {row[0] for row in (await h.execute(live_people(100_000))).all()}
    if newcomer not in listed:
        raise CheckFailedError("the person the staff list made is not on People")
    if leaver in listed:
        raise CheckFailedError("a leaver on the staff list was made a person")
    joined = await h.execute(
        select(PrincipalIdentityRow.principal_id).where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.identity_hash == digest_of(_address(h, newcomer)),
            PrincipalIdentityRow.deleted_at.is_(None),
        )
    )
    if joined.scalar_one_or_none() != newcomer:
        raise CheckFailedError("the person the staff list made is not joined to their row")
    again = await provide_people(h.sessions, roster, now=h.now, new_id=lambda: leaver)
    if again.made != 0:
        raise CheckFailedError("a second read of the same list made another person")


@check(
    leaves=("M1.6.20", "M1.6.21"),
    sentence=(
        "On reserved people: moving two of them to the other reserved department in one statement, "
        "as People moves them, puts both there and records each move under the person who made it; "
        "one already there is not recorded as moved; and the Starter pack step, with departments "
        "managed on People, reads where People put them and not where the list says."
    ),
)
async def people_moved_on_people_are_recorded_and_read_by_the_sync(
    h: Harness,
) -> None:
    first, second = RESERVED_DEPARTMENTS
    await h.found_departments()
    one, two, there = (
        h.principal(first, "one"),
        h.principal(first, "two"),
        h.principal(second, "one"),
    )
    for pid, department in ((one, first), (two, first), (there, second)):
        await h.person(pid, department=department)
        await _joined(h, pid)
    await h.execute(*h.attributed(), moving_people([one, two], second))
    await h.execute(*h.attributed(), moving_people([there], second))

    placed = await h.execute(
        select(PrincipalRow.id, PrincipalRow.primary_department).where(
            PrincipalRow.id.in_([one, two, there])
        )
    )
    if {str(pid): str(slug) for pid, slug in placed.all()} != dict.fromkeys(
        (one, two, there), second
    ):
        raise CheckFailedError("the people moved are not in the department they were moved to")
    recorded = await h.execute(
        select(AuditEntryRow.subject, AuditEntryRow.actor_id, AuditEntryRow.details).where(
            AuditEntryRow.action == "organisation",
            AuditEntryRow.subject.in_([f"principal:{pid}" for pid in (one, two, there)]),
        )
    )
    moves = {
        (
            str(subject),
            str(actor),
            str((details or {}).get("change")),
            str((details or {}).get("department")),
        )
        for subject, actor, details in recorded.all()
    }
    if moves != {(f"principal:{pid}", h.actor, "moved", second) for pid in (one, two)}:
        raise CheckFailedError("a move is not on the ledger under its mover, or a non-move is")

    listed = Roster(
        source=SOURCE,
        complete=True,
        asserts=DEFAULT_TRUST["lark"],
        people=tuple(
            StaffRecord(_address(h, pid), "Acceptance check", department=first, leads=True)
            for pid in (one, two)
        ),
    )
    as_placed = as_the_console_places_them(listed, {_address(h, pid): second for pid in (one, two)})
    if {(p.department, p.leads) for p in as_placed.people} != {(second, False)}:
        raise CheckFailedError("under People the sync still reads the list's department or lead")
