"""The staff sync's accounts step: make, link, close and open sign-in accounts, and their people.

`brain.identity.staff_accounts` decides who has an account and `brain.connectors.sign_in_accounts`
makes the calls; this runs them after the roster is applied, in the worker, with the accounts
client's secret leased from the vault for the run (`connector_keys/sign_in_accounts`, which the
release writes). It fails the way the heads' reach and the Starter packs do: logged, reported on the
run, and never undoing the roster.

**Each account the sync makes or finds is a Brain person the same way a hand-made link is.** A new
account's person is made (`auth.principal`, a staff or contractor principal in the department the
source names when a department here answers to it) and the account is bound to them by
`brain.identity.sign_in_binding.SignInBindings.bind`, the Sign-in links screen's own write, so the
binding, its member grant and its ledger entry are the ones a person linking by hand would make,
attributed to the source's sync. A person found by an existing link is not made again.

**The work address is bound as an email identity that carries nothing.** Every part of the sync
that follows a roster row to a person (the Starter packs, a head's audit reach, the leavers'
agents, the organisation's placements) joins on an email binding of the address's digest, and
nothing wrote one for a person the sync brings in. It is written at `Assurance.UNVERIFIED`, which
`brain.gate.admission` gives no verb on any channel: it records which roster row the person was made
for and admits nothing from that mailbox. A person binds their mailbox to the email channel the
usual way. See `THE_ROSTER_JOIN_IS_AN_EMAIL_BINDING_THAT_ADMITS_NOTHING`.

**This step closes and opens accounts; it does not disable anybody.** Whether a Brain person may
sign in or ask is `brain.identity.standing`'s, which the same run applies to every person the list
can be joined to, however their sign-in was made, and which lets back in only whom the list kept
out (package 2 of needs-rupash 115, 2026-09-30). Until then this step disabled and enabled the
person behind each account it closed and opened, which was a second place deciding the same thing
and the only one that could re-enable somebody an administrator had disabled by hand. An account
whose person the standing step keeps in as the last administrator is not closed either
(`keep_open`).

**Nothing is sent.** See `staff_accounts.NOTHING_IS_SENT_AND_A_PERSON_ASKS_FOR_THEIR_OWN_LINK`.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.sign_in_accounts import (
    KEY_SLOT,
    SignInServiceError,
    accounts_of,
    close,
    make,
    mark,
    new_user,
    realm_of,
    reopen,
    token,
)
from brain.connectors.staff_directories import Fetch
from brain.core.principal import Employment
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.organisation_sync import department_key, sync_actor, sync_trace
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.sign_in_binding import SignInBindingRefusedError, SignInBindings
from brain.identity.staff_accounts import (
    AccountPlan,
    HeldAccount,
    account_plan,
    allowed_types,
)
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import EmploymentType, Roster, StaffRecord
from brain.identity.starter_pack_sync import registered_by_name
from brain.install import InstallError, value_of
from brain.ops.connectable import key_reference
from brain.ops.connector_sync_run import ConnectorKeyAbsentError, ConnectorKeys, key_detail
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.starter_pack_store import registered_departments
from brain.tables.audit import attributed_to
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

log = structlog.get_logger()

#: Why the roster's join to a person is written at the assurance that admits nothing.
THE_ROSTER_JOIN_IS_AN_EMAIL_BINDING_THAT_ADMITS_NOTHING: Final = (
    "The sync follows a roster row to its person through an email binding of the address's "
    "digest, and a person the sync makes has none. It is written unverified, which admits no verb "
    "on any channel: it says which row the person was made for, and a message from that mailbox "
    "is still a stranger's until the person binds it themselves."
)

#: The vault slot the accounts client's `<client id>:<secret>` is kept in. The release writes it.
ACCOUNTS_SLOT: Final = KEY_SLOT

#: The installation setting naming the employment types that may use the Brain.
ACCOUNT_TYPES_SETTING: Final = "INSTALL_ACCOUNT_EMPLOYMENT_TYPES"

#: The employment types whose people are contractors rather than staff on a Brain person.
CONTRACTED: Final[frozenset[EmploymentType]] = frozenset(
    {
        EmploymentType.OUTSOURCED,
        EmploymentType.LABOUR_DISPATCH,
        EmploymentType.CONSULTANT,
        EmploymentType.CONTRACTOR,
    }
)

#: What a new person's id begins with, as every person the setup wizard makes.
PRINCIPAL_PREFIX: Final = "u_"

#: The digest the sync's own ledger entries carry for a reach: a sync has none.
NO_REACH: Final = "0" * 32

# The sentences a run leaves, which name no person.
NO_KEY: Final = (
    "Sign-in accounts: none made or closed, because the accounts client's credential is not in "
    "the vault yet. The next release writes it."
)
NO_ISSUER: Final = (
    "Sign-in accounts: none made, because the worker is not given this install's sign-in address "
    "(INSTALL_OIDC_ISSUER), so it cannot tell which realm to make them in."
)
HOW_PEOPLE_GET_IN: Final = (
    "Nobody was sent anything. Each person sets a password with Forgot password on the sign-in "
    "page, which needs the sign-in service's email settings."
)


@dataclass(frozen=True)
class AccountRun:
    """What the accounts step came to, in sentences that name nobody."""

    sentences: tuple[str, ...]
    plan: AccountPlan | None = None


def employment_of(person: StaffRecord) -> Employment:
    """A contracted type is a contractor on the Brain; everybody else is staff."""
    return Employment.CONTRACTOR if person.employment_type in CONTRACTED else Employment.STAFF


async def _bound(session: AsyncSession, channel: Channel, digest: str) -> str | None:
    found = (
        await session.execute(
            select(PrincipalIdentityRow.principal_id).where(
                PrincipalIdentityRow.channel == channel.value,
                PrincipalIdentityRow.identity_hash == digest,
                PrincipalIdentityRow.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return None if found is None else str(found)


async def person_for(
    sessions: async_sessionmaker[AsyncSession],
    *,
    account: HeldAccount,
    person: StaffRecord,
    issuer: str,
    actor: str,
    now: datetime,
    trace_id: str,
    place: bool = True,
) -> str:
    """The Brain person behind this account, made and bound if there is none. Returns their id.

    Found by the account's sign-in link first, then by the address's email binding; made only when
    neither exists. The sign-in link is written by `SignInBindings.bind`, the screen's own write.
    A person made is placed in the department the list names when `place`, and in none when
    departments are managed on People
    (`brain.identity.departments_from.UNDER_THE_CONSOLE_THE_SYNC_MOVES_NOBODY`).
    """
    email_digest = digest_of(person.work_address)
    async with sessions() as session, session.begin():
        signed = await _bound(session, SIGN_IN_CHANNEL, subject_digest(issuer, account.account_id))
        mailbox = await _bound(session, Channel.EMAIL, email_digest)
        principal_id = signed or mailbox
        if principal_id is None:
            departments = {
                str(slug): str(name)
                for slug, name in (await session.execute(registered_departments())).all()
            }
            principal_id = f"{PRINCIPAL_PREFIX}{uuid.uuid4().hex}"
            for statement in attributed_to(actor_id=actor, ent_hash=NO_REACH, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                insert(PrincipalRow).values(
                    id=principal_id,
                    kind="human",
                    employment=employment_of(person).value,
                    display_name=person.display_name,
                    primary_department=registered_by_name(departments).get(
                        department_key(person.department)
                    )
                    if place
                    else None,
                )
            )
        if mailbox is None:
            for statement in attributed_to(actor_id=actor, ent_hash=NO_REACH, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                insert(PrincipalIdentityRow).values(
                    channel=Channel.EMAIL.value,
                    identity_hash=email_digest,
                    principal_id=principal_id,
                    bound_at=now,
                    assurance=int(Assurance.UNVERIFIED),
                )
            )
    if signed is None:
        try:
            await SignInBindings(sessions, issuer).bind(
                account.account_id,
                principal_id=principal_id,
                bound_by=actor,
                now=now,
                ent_hash=NO_REACH,
                trace_id=trace_id,
            )
        except SignInBindingRefusedError as refused:
            # A person already signing in with another account is left as they are, and said.
            log.info("staff_accounts.link_refused", reason=refused.reason.value)
    return principal_id


async def signs_in_as(
    sessions: async_sessionmaker[AsyncSession], issuer: str, account: HeldAccount
) -> str | None:
    """The Brain person this account signs in as, or None when it signs nobody in."""
    async with sessions() as session, session.begin():
        return await _bound(session, SIGN_IN_CHANNEL, subject_digest(issuer, account.account_id))


async def provide_accounts(
    *,
    sessions: async_sessionmaker[AsyncSession],
    roster: Roster,
    stable_ids: Mapping[str, str],
    keys: ConnectorKeys,
    fetch: Fetch,
    env: Mapping[str, str] | None,
    now: datetime,
    absent_is_gone: bool,
    trial: bool = False,
    keep_open: frozenset[str] = frozenset(),
    place: bool = True,
) -> AccountRun:
    """Plan the accounts this roster supports and carry the plan out, unless this is a trial.

    `keep_open` is the principals the standing step keeps in as the last administrators, whose
    accounts are not closed whatever the plan says. Never raises for the sign-in service or the
    vault: a refusal is a sentence on the run and the next night tries again.
    """
    try:
        issuer = value_of("INSTALL_OIDC_ISSUER", env)
    except InstallError:
        return AccountRun(sentences=(NO_ISSUER,))
    try:
        realm = realm_of(issuer)
    except SignInServiceError as unnamed:
        return AccountRun(sentences=(f"Sign-in accounts: none made. {unnamed}",))
    allowed = allowed_types(value_of(ACCOUNT_TYPES_SETTING, env))
    lease = keys.lease(key_reference(ACCOUNTS_SLOT), now=now)
    try:
        try:
            credential = lease.key()
        except ConnectorKeyAbsentError:
            return AccountRun(sentences=(NO_KEY,))
        except SecretsUnavailableError as unavailable:
            return AccountRun(
                sentences=(f"Sign-in accounts: none made. {key_detail(unavailable)}",)
            )
        bearer = await token(fetch, realm, credential)
        accounts = await accounts_of(
            fetch,
            realm,
            bearer,
            source=roster.source,
            emails=[one.work_address for one in roster.people],
        )
        plan = account_plan(
            roster,
            stable_ids=stable_ids,
            accounts=accounts,
            allowed=allowed,
            absent_is_gone=absent_is_gone,
        )
        if trial:
            return AccountRun(sentences=(*plan.sentences(), HOW_PEOPLE_GET_IN), plan=plan)
        actor = sync_actor(roster.source)
        trace_id = sync_trace("staff-accounts", now)
        for new in plan.to_make:
            account = await make(
                fetch,
                realm,
                bearer,
                new_user(
                    email=new.person.work_address,
                    display_name=new.person.display_name,
                    source=roster.source,
                    stable_id=new.stable_id,
                ),
            )
            await person_for(
                sessions,
                account=account,
                person=new.person,
                issuer=issuer,
                actor=actor,
                now=now,
                trace_id=trace_id,
                place=place,
            )
        for linked in plan.to_link:
            if linked.needs_marking:
                await mark(
                    fetch,
                    realm,
                    bearer,
                    linked.account,
                    source=roster.source,
                    stable_id=linked.stable_id,
                )
            await person_for(
                sessions,
                account=linked.account,
                person=linked.person,
                issuer=issuer,
                actor=actor,
                now=now,
                trace_id=trace_id,
                place=place,
            )
        for account in plan.to_enable:
            await reopen(fetch, realm, bearer, account)
        for account in plan.to_disable:
            if await signs_in_as(sessions, issuer, account) in keep_open:
                continue
            await close(fetch, realm, bearer, account)
    except SignInServiceError as refused:
        return AccountRun(sentences=(f"Sign-in accounts: stopped. {refused}",))
    finally:
        lease.close(now)
    return AccountRun(sentences=(*plan.sentences(), HOW_PEOPLE_GET_IN), plan=plan)
