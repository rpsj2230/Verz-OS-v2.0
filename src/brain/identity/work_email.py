"""A person's work email, added on their People page, and the join it makes with the staff list.

**Duplicates are found by address and never by name**, which is the owner's rule of 2026-09-30.
The staff sync makes a Brain person for every active address on the list that no person is joined
to (`brain.ops.staff_people_run`). A person made by hand before the list existed, the first
administrator above all, is joined to no address, so the list makes a second person for theirs.
Two people with one name are not evidence of anything, and matching on a name would hand a
stranger's row whatever the named person holds. An address is unique to a person, so binding the
hand-made person's work address is what lets the two be told to be one. See
`A_DUPLICATE_IS_FOUND_BY_ADDRESS_AND_NEVER_BY_NAME`.

**The join is automatic only when it can take nothing from anybody.** When the address is already
bound to a person the list made, and that person has never signed in and holds nothing but what
the sync itself wrote (a Starter pack, a head's audit reach, a team the list names), the list's
person is disabled and retired, and the address is bound to the person the page is about. The
next sync then follows the address to them. Anything else waits for a confirmation on the page,
and a list person who signs in with an account of their own is never joined here, because a person
has one way in and retiring the one they use would lock them out. See
`A_JOIN_IS_AUTOMATIC_ONLY_WHEN_IT_TAKES_NOTHING`.

**Every step is recorded by the triggers that already record it**: unbinding the list person's
address and binding it to this person are `channel_binding` entries (`0118`), and disabling the list
person is a `principal_state` entry (`0095b`), each attributed to whoever pressed. Rejected: a new
ledger action for a join, which would need a migration for three entries the ledger already writes.

**Nothing here moves a grant.** What the list person held that the sync wrote, the sync writes
again for the joined person on its next run; what an administrator granted them is named in the
confirmation and not carried over, because a join is not a grant and carrying reach across people is
the helpful union `brain.resolution.canonical` warns about.

Task ids: M1.10.4
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Select, Update, exists, func, insert, or_, select, update
from sqlalchemy.sql.dml import Insert

from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.principal_directory import SIGN_IN_CHANNEL
from brain.identity.staff_sync import ROSTER_PREFIX
from brain.tables.agent import AgentRow
from brain.tables.gate import CapabilityGrantRow, CapabilityPackAssignmentRow
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow, SessionRow
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow
from brain.tables.role_grant import RoleGrantRow

#: Why a duplicate is found by address and never by name.
A_DUPLICATE_IS_FOUND_BY_ADDRESS_AND_NEVER_BY_NAME: Final = (
    "A work address belongs to one person and a name does not: two people share a name every day, "
    "and joining on one would hand a stranger's row whatever the named person holds. So a person "
    "made by hand is told to be the staff list's person for the same address only once their work "
    "address is bound to them, and never because the two names match."
)

#: Why the join is automatic only for a list person who has nothing to lose.
A_JOIN_IS_AUTOMATIC_ONLY_WHEN_IT_TAKES_NOTHING: Final = (
    "Retiring the staff list's person is harmless when they have never signed in and hold nothing "
    "the sync did not write, because the sync writes that again for the joined person. When they "
    "have signed in, or somebody granted them something, retiring them takes it away, so the page "
    "asks first; and one who signs in with an account of their own is not joined here at all, "
    "because a person has one way in and retiring theirs would lock them out."
)

#: The longest address a mailbox can have.
ADDRESS_CHARS: Final = 254

_ADDRESS: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class WorkEmailError(ValueError):
    """Raised for an address no mailbox could have."""


def work_address(typed: str) -> str:
    """The address as typed, trimmed, or refused. The digest folds its case."""
    address = typed.strip()
    if len(address) > ADDRESS_CHARS or _ADDRESS.fullmatch(address) is None:
        msg = "Type the person's work email, like name@company.example."
        raise WorkEmailError(msg)
    return address


class Joining(enum.StrEnum):
    """What adding a work email comes to."""

    #: Nobody holds the address: it is bound to this person, and the list will find them.
    BOUND = "bound"
    #: The list's person for the address is retired and the address bound to this person.
    JOINED = "joined"
    #: The list's person has signed in or holds something: the page asks before joining.
    ASK = "ask"
    #: The list's person signs in with an account of their own: not joined here.
    SIGNS_IN_ELSEWHERE = "signs_in_elsewhere"
    #: This person already has a work email.
    ALREADY = "already"


@dataclass(frozen=True)
class Holder:
    """The person the address is bound to now, as the join needs to know them."""

    principal_id: str
    #: Bound to a sign-in, so retiring them would end the way in they use.
    signs_in: bool
    #: Has ever had a session, whether or not a sign-in is still bound.
    signed_in: bool
    #: Holds a grant, pack, role, team, lead or agent somebody other than the sync gave them.
    holds_own: bool


def decide(*, has_email: bool, holder: Holder | None, confirmed: bool) -> Joining:
    """What adding the address does. See the two named reasons.

    A holder that is this very person cannot reach here: their binding is a work email, so
    `has_email` is already true.
    """
    if has_email:
        return Joining.ALREADY
    if holder is None:
        return Joining.BOUND
    if holder.signs_in:
        return Joining.SIGNS_IN_ELSEWHERE
    if (holder.signed_in or holder.holds_own) and not confirmed:
        return Joining.ASK
    return Joining.JOINED


#: What the page is told, one sentence per outcome. None names the other person.
TOLD: Final[dict[Joining, str]] = {
    Joining.BOUND: (
        "The work email is added. The next staff sync finds this person by it, and makes nobody "
        "else for it."
    ),
    Joining.JOINED: (
        "The work email is added, and the person the staff list had made for it is joined into "
        "this one and no longer listed. The next staff sync finds this person by it."
    ),
    Joining.ASK: (
        "The staff list's person for this email has signed in or holds something somebody gave "
        "them. Joining them into this person retires them, and what was given to them is not "
        "carried over."
    ),
    Joining.SIGNS_IN_ELSEWHERE: (
        "The staff list's person for this email signs in with an account of their own, so they "
        "are not joined here. Unlink that sign-in on Sign-in links first."
    ),
    Joining.ALREADY: "This person already has a work email.",
}


# ------------------------------------------------------------------------------ the statements
def email_of(principal_id: str) -> Select[tuple[str]]:
    """The digest of this person's live work email binding, if they have one."""
    return (
        select(PrincipalIdentityRow.identity_hash)
        .where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.principal_id == principal_id,
            PrincipalIdentityRow.deleted_at.is_(None),
        )
        .limit(1)
    )


def holder_of(digest: str) -> Select[tuple[str]]:
    """Who a live email binding of this digest points at."""
    return select(PrincipalIdentityRow.principal_id).where(
        PrincipalIdentityRow.channel == Channel.EMAIL.value,
        PrincipalIdentityRow.identity_hash == digest,
        PrincipalIdentityRow.deleted_at.is_(None),
    )


def holder_facts(principal_id: str) -> Select[tuple[bool, bool, bool]]:
    """Whether this person signs in, has signed in, and holds anything the sync did not write."""
    not_the_sync = ~CapabilityGrantRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True)
    signs_in = exists().where(
        PrincipalIdentityRow.principal_id == principal_id,
        PrincipalIdentityRow.channel == SIGN_IN_CHANNEL.value,
        PrincipalIdentityRow.deleted_at.is_(None),
    )
    signed_in = exists().where(SessionRow.principal_id == principal_id)
    holds_own = or_(
        exists().where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.deleted_at.is_(None),
            not_the_sync,
        ),
        exists().where(
            CapabilityPackAssignmentRow.principal_id == principal_id,
            CapabilityPackAssignmentRow.deleted_at.is_(None),
            ~CapabilityPackAssignmentRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True),
        ),
        exists().where(
            RoleGrantRow.principal_id == principal_id,
            RoleGrantRow.deleted_at.is_(None),
            ~RoleGrantRow.granted_by.startswith(ROSTER_PREFIX, autoescape=True),
        ),
        exists().where(
            TeamMembershipRow.principal_id == principal_id,
            TeamMembershipRow.ended_at.is_(None),
            ~TeamMembershipRow.added_by.startswith(ROSTER_PREFIX, autoescape=True),
        ),
        exists().where(
            DepartmentLeadRow.principal_id == principal_id,
            DepartmentLeadRow.ended_at.is_(None),
            ~DepartmentLeadRow.appointed_by.startswith(ROSTER_PREFIX, autoescape=True),
        ),
        exists().where(AgentRow.owner_id == principal_id),
    )
    return select(signs_in, signed_in, holds_own)


def unbinding(digest: str) -> Update:
    """Retire the live email binding of this digest, stamped by its own statement (`0045`)."""
    return (
        update(PrincipalIdentityRow)
        .where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.identity_hash == digest,
            PrincipalIdentityRow.deleted_at.is_(None),
        )
        .values(deleted_at=func.statement_timestamp())
    )


def binding(principal_id: str, digest: str) -> Insert:
    """The work email bound to this person, at the assurance that admits nothing."""
    return insert(PrincipalIdentityRow).values(
        channel=Channel.EMAIL.value,
        identity_hash=digest,
        principal_id=principal_id,
        bound_at=func.statement_timestamp(),
        assurance=int(Assurance.UNVERIFIED),
    )


def disabling(principal_id: str) -> Update:
    """Disable the list's person, which `0095b` records and `0003` ends every session of."""
    return (
        update(PrincipalRow)
        .where(PrincipalRow.id == principal_id, PrincipalRow.disabled_at.is_(None))
        .values(disabled_at=func.statement_timestamp())
    )


def retiring(principal_id: str) -> Update:
    """Retire the list's person, so People no longer lists them."""
    return (
        update(PrincipalRow)
        .where(PrincipalRow.id == principal_id, PrincipalRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
    )
