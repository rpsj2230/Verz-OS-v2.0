"""Which of the people a staff source lists get a sign-in account, decided without a connection.

The owner decided on 2026-09-29 (needs-rupash 115, "B now, A next") that the staff sync gives each
active person a Brain account, and then narrowed how they first get in: "do remember not to send the
Link to them and the flow should be that they need to click Forget Password on the login page and
then they will get the link. I don't want to send the bulk email to all." So an account is made with
the person's work address, no password and the second factor required, and nothing is ever sent: a
person sets their password by pressing Forgot password on the sign-in page, which is the sign-in
service's own reset email, sent only because they asked. `brain.connectors.sign_in_accounts` makes
the calls and `brain.ops.staff_accounts_run` runs them; this decides who.

**Who may have an account.** Somebody the source says is active, whose employment type the install
allows (`INSTALL_ACCOUNT_EMPLOYMENT_TYPES`, every type but outsourced by default). A source that
records no type for somebody lets them in, because three of the six sources record none and refusing
the unknown would give a whole company no accounts. Suspended, left and not-activated people get
none. See `AN_ACCOUNT_FOR_THE_ACTIVE_AND_THE_ALLOWED`.

**Nobody is given two accounts.** An account the sync made carries the source and the source's
stable identifier for the person as attributes, and is found by them first, so a changed address is
the same account; one nobody marked is found by its work address and linked rather than duplicated,
and a re-run only fills what is missing. See `A_PERSON_IS_FOUND_BEFORE_ANYBODY_IS_MADE`.

**The sync closes only the accounts it made.** An account a person made by hand (the first
administrator's, one made before the sync existed) is linked and never disabled: which of those
somebody keeps is a person's decision, and the sync disabling the only administrator because a
directory said so would lock a company out of its own install. A leaver's or suspended person's
account the sync made is disabled and their Brain sessions ended; one the source lists as active
again, or whose type is allowed again, is enabled. Somebody merely absent from a list that did not
promise to be complete keeps their account, on `dry_run`'s rule. See
`THE_SYNC_CLOSES_ONLY_THE_ACCOUNTS_IT_MADE`.

**A list anybody can edit makes no account.** Only a source trusted to say which department
somebody is in, which is a directory an administrator controls, gives accounts; a spreadsheet or a
Google Sheet, which whoever holds the link can edit, plans nothing. See
`A_LIST_ANYBODY_CAN_EDIT_MAKES_NO_ACCOUNT`, and needs-rupash 119, which asks the owner to confirm
it.

Rejected: an invitation email (Keycloak's execute-actions email) when an account is made, which was
the first design and what the owner refused. Rejected: a password generated here and sent anywhere,
which is a secret in transit and a reason for somebody to be told one.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from brain.identity.staff_source import (
    Asserts,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)

# ------------------------------------------------------------------ written-down reasons
#: Who is given a sign-in account.
AN_ACCOUNT_FOR_THE_ACTIVE_AND_THE_ALLOWED: Final = (
    "A person the staff source says is active, of an employment type the install allows, is given "
    "an account; nobody suspended, gone or never activated is. A source that records no type lets "
    "a person in, because refusing the unknown would give a whole company no accounts."
)

#: Why the account is looked for before one is made.
A_PERSON_IS_FOUND_BEFORE_ANYBODY_IS_MADE: Final = (
    "An account is found by the source and its stable identifier for the person first, so a "
    "changed address is still the same account, then by the work address, so an account somebody "
    "made by hand is linked rather than duplicated. A run makes only what is missing."
)

#: Why the sync disables only what it made.
THE_SYNC_CLOSES_ONLY_THE_ACCOUNTS_IT_MADE: Final = (
    "An account a person made is theirs to close. The sync disables only accounts it made, when "
    "their person is suspended, gone or of a type no longer allowed, and enables one again when "
    "the source lists them as active and allowed; it never touches the first administrator's."
)

#: Why nothing is ever sent.
NOTHING_IS_SENT_AND_A_PERSON_ASKS_FOR_THEIR_OWN_LINK: Final = (
    "The owner decided that no link is sent to anybody. An account is made with no password, and "
    "the person sets one with Forgot password on the sign-in page, which emails them the sign-in "
    "service's own reset link because they asked; the second factor is set at the first sign-in."
)

#: Why a list anybody with its link can edit makes no account.
A_LIST_ANYBODY_CAN_EDIT_MAKES_NO_ACCOUNT: Final = (
    "An account is a way in, so it is made only from a source an administrator controls: one "
    "trusted to say which department somebody is in, which the directories are and a spreadsheet "
    "is not. A row anybody with a sheet's link adds would otherwise be an account for an address "
    "whoever added it can read (needs-rupash 119)."
)

#: The sentence a run from such a source leaves.
NO_ACCOUNTS_FROM_AN_OPEN_LIST: Final = (
    "Sign-in accounts: none made, because this staff list can be edited by anybody who has its "
    "link. Accounts are made from a company directory: Lark, Google Workspace, Microsoft Entra or "
    "LDAP."
)

#: The employment types allowed when an install has said nothing: every one but outsourced.
DEFAULT_ALLOWED: Final[frozenset[EmploymentType]] = frozenset(
    one for one in EmploymentType if one is not EmploymentType.OUTSOURCED
)

#: The setting's one word that allows nobody: the staff sync then makes no account, and closes the
#: ones it made. How an install that does not want the sync to make accounts says so.
NOBODY: Final = "none"

#: How somebody on the list first signs in, as the Staff sources screen says it.
HOW_A_PERSON_FIRST_SIGNS_IN: Final = (
    "The staff sync gives each active person on this list a sign-in account and sends nobody "
    "anything. Tell people their account is ready: each one opens the sign-in page, presses Forgot "
    "password, enters their work email, sets a password from the link that arrives, and then sets "
    "up their second factor."
)

#: What stops that, and what to fill in, as the Staff sources screen says it.
WITHOUT_EMAIL_SETTINGS: Final = (
    "If the sign-in service has no email settings, nobody can set a password yet, because Forgot "
    "password has nothing to send its link with. In Keycloak, open this install's realm, then "
    "Realm settings, then Email, and fill in the From address, your mail server's Host and Port, "
    "SSL or StartTLS as your mail server requires, and its username and password if it asks for "
    "them. Press Test connection, then Save."
)

#: The sentence an administrator can pass on to somebody whose account is ready.
YOUR_ACCOUNT_IS_READY: Final = (
    "Your account is ready. Go to the sign-in page, press Forgot password "
    "and enter your work email."
)


class AccountRefusal(enum.StrEnum):
    """Why somebody the source lists has no account. A count of each is reported, never a name."""

    NOT_ACTIVE = "not_active"
    TYPE_NOT_ALLOWED = "type_not_allowed"


@dataclass(frozen=True)
class HeldAccount:
    """One sign-in account as the sign-in service holds it."""

    account_id: str
    email: str
    enabled: bool
    #: The source and the source's identifier for the person, where the sync made or linked it.
    source: str = ""
    stable_id: str = ""
    #: True for an account the sync made, which is the only kind it may disable.
    made_by_sync: bool = False


@dataclass(frozen=True)
class NewAccount:
    """An account to make, for this person."""

    person: StaffRecord
    stable_id: str


@dataclass(frozen=True)
class Linked:
    """An account that exists and is this person's, and whether it needs marking as the sync's."""

    person: StaffRecord
    account: HeldAccount
    stable_id: str
    #: True where the account is not yet marked with the source and identifier.
    needs_marking: bool


@dataclass(frozen=True)
class AccountPlan:
    """What one run does to sign-in accounts. Lists to act on, and counts to report."""

    to_make: tuple[NewAccount, ...] = ()
    #: Every eligible person whose account exists, for binding and marking; nothing is made.
    to_link: tuple[Linked, ...] = ()
    to_enable: tuple[HeldAccount, ...] = ()
    to_disable: tuple[HeldAccount, ...] = ()
    refused: Mapping[AccountRefusal, int] = field(default_factory=dict)
    #: Why fewer accounts were closed than a reader might expect, in words.
    withheld: tuple[str, ...] = ()

    def sentences(self) -> tuple[str, ...]:
        """What the plan does, in counts, for the run's report."""
        found = [
            f"Sign-in accounts: {len(self.to_make)} made, {len(self.to_enable)} opened again, "
            f"{len(self.to_disable)} closed."
        ]
        reasons = {
            AccountRefusal.NOT_ACTIVE: "suspended, gone or never activated",
            AccountRefusal.TYPE_NOT_ALLOWED: "of an employment type that may not use the Brain",
        }
        said = [
            f"{self.refused[one]} {reasons[one]}" for one in AccountRefusal if self.refused.get(one)
        ]
        if said:
            found.append(f"No account for {', '.join(said)}.")
        found.extend(self.withheld)
        return tuple(found)


def may_have_an_account(person: StaffRecord, allowed: Collection[EmploymentType]) -> bool:
    """Whether this person may have a sign-in account. See the constant."""
    if person.standing is not EmploymentStatus.ACTIVE:
        return False
    return person.employment_type is None or person.employment_type in allowed


def account_plan(
    roster: Roster,
    *,
    stable_ids: Mapping[str, str],
    accounts: Iterable[HeldAccount],
    allowed: Collection[EmploymentType],
    absent_is_gone: bool,
) -> AccountPlan:
    """Who is given an account, who is linked, and whose account is closed or opened again.

    `stable_ids` is the reading's casefolded address to the source's identifier; a person with none
    is keyed by their address. `absent_is_gone` is the roster's own answer to whether somebody it no
    longer lists has left: complete, and applied before. Only accounts of this roster's source are
    closed for absence. A source not trusted with departments plans nothing at all; see
    `A_LIST_ANYBODY_CAN_EDIT_MAKES_NO_ACCOUNT`.
    """
    if Asserts.DEPARTMENT not in roster.asserts:
        return AccountPlan(withheld=(NO_ACCOUNTS_FROM_AN_OPEN_LIST,))
    held = tuple(accounts)
    by_id = {(one.source, one.stable_id): one for one in held if one.source and one.stable_id}
    by_email = {one.email.strip().casefold(): one for one in held if one.email.strip()}
    refused: dict[AccountRefusal, int] = {}
    to_make: list[NewAccount] = []
    to_link: list[Linked] = []
    to_enable: list[HeldAccount] = []
    to_disable: list[HeldAccount] = []
    claimed: set[str] = set()

    for person in sorted(roster.people, key=lambda one: one.work_address.casefold()):
        address = person.work_address.strip().casefold()
        stable = stable_ids.get(address, "") or address
        account = by_id.get((roster.source, stable)) or by_email.get(address)
        if account is not None:
            claimed.add(account.account_id)
        if not may_have_an_account(person, allowed):
            reason = (
                AccountRefusal.NOT_ACTIVE
                if person.standing is not EmploymentStatus.ACTIVE
                else AccountRefusal.TYPE_NOT_ALLOWED
            )
            refused[reason] = refused.get(reason, 0) + 1
            if account is not None and account.enabled and account.made_by_sync:
                to_disable.append(account)
            continue
        if account is None:
            to_make.append(NewAccount(person=person, stable_id=stable))
            continue
        to_link.append(
            Linked(
                person=person,
                account=account,
                stable_id=stable,
                needs_marking=(account.source, account.stable_id) != (roster.source, stable),
            )
        )
        if not account.enabled and account.made_by_sync:
            to_enable.append(account)

    withheld: list[str] = []
    ours = [
        one
        for one in held
        if one.source == roster.source and one.made_by_sync and one.account_id not in claimed
    ]
    if absent_is_gone:
        to_disable.extend(one for one in ours if one.enabled)
    elif any(one.enabled for one in ours):
        withheld.append(
            "Accounts of people the staff list no longer names are kept, because the list did not "
            "promise to be complete or has never been applied."
        )
    return AccountPlan(
        to_make=tuple(to_make),
        to_link=tuple(to_link),
        to_enable=tuple(to_enable),
        to_disable=tuple(sorted(to_disable, key=lambda one: one.account_id)),
        refused=refused,
        withheld=tuple(withheld),
    )


def allowed_types(value: str) -> frozenset[EmploymentType]:
    """The employment types a setting's comma-separated value names; the default for a blank one.

    `NOBODY` alone is the empty set. A word no type carries is refused by the setting's own check
    before it is saved, so here it is ignored rather than raised: a sync must not stop over a value
    somebody wrote by hand.
    """
    words = [one.strip().casefold() for one in value.split(",") if one.strip()]
    if not words:
        return DEFAULT_ALLOWED
    if words == [NOBODY]:
        return frozenset()
    known = {one.value: one for one in EmploymentType}
    return frozenset(known[one] for one in words if one in known)


def setting_value(types: Sequence[EmploymentType]) -> str:
    """The setting's value for these types, in the enum's order."""
    return ",".join(one.value for one in EmploymentType if one in set(types))
