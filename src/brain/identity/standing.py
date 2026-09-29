"""Who the staff list keeps out of the Brain, and who it lets back in, decided without a connection.

The owner asked on 2026-09-29 (needs-rupash 115, item 2) that somebody the staff source says is
suspended, has left or never activated can never sign in or ask, and that outsourced people follow
the install's setting. This decides it for every Brain person the list can be joined to, whoever
made their sign-in: an account the staff sync made, one an administrator made, the first
administrator's own. `brain.ops.standing_run` carries it out.

**Kept out is disabled, the one refusal every door already makes.** A disabled principal is absent
to the gate on every channel (`brain.identity.principal_store.principal_from`), and 0003's cascade
ends their sessions and makes their grants inert in the statement that disables them, so nothing
here adds a check to the request path. Rejected: a second check at admission reading the staff
list on every request, which would be a second refusal to keep in step with the first and a read
of the roster on the path every question takes. See `A_PERSON_THE_LIST_KEEPS_OUT_IS_DISABLED`.

**The list lets back in only whom it kept out.** A person an administrator disabled stays disabled
when the list says they are active, because that was a person's decision and the nightly run is
not one. Who disabled somebody last is read off the ledger's own `principal_state` entry. See
`THE_LIST_LETS_BACK_IN_ONLY_WHOM_IT_KEPT_OUT`.

**The last administrator is never kept out.** A directory marking the only administrator suspended
would otherwise lock a company out of its own install with nobody able to sign in to undo it. They
are kept in, and the run says so in a count. See `THE_LAST_ADMINISTRATOR_IS_NEVER_KEPT_OUT`.

**Where somebody stands is the reading's word, over what the roster held.** A person the source
lists now is judged by what it says today, a person it no longer lists by the mark the roster keeps,
and a person the roster has never held (an inactive newcomer, whom the roster does not add) by the
reading alone, so a hand-made account for somebody Lark never activated is still kept out.

Task ids: M1.6.14
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

from brain.identity.staff_roster import MemberWrite, StoredMember, Write, digest_of
from brain.identity.staff_source import EmploymentStatus, EmploymentType, StaffRecord

# ------------------------------------------------------------------ written-down reasons
A_PERSON_THE_LIST_KEEPS_OUT_IS_DISABLED: Final = (
    "Somebody the staff list says is suspended, gone or never activated, or whose employment type "
    "the install does not allow, is disabled: the one refusal every channel and every session "
    "already makes. Nothing is added to the request path."
)

THE_LIST_LETS_BACK_IN_ONLY_WHOM_IT_KEPT_OUT: Final = (
    "A person the staff list disabled is enabled again when it lists them as active and allowed. "
    "A person an administrator disabled stays disabled whatever the list says, because the last "
    "word on them was a person's."
)

THE_LAST_ADMINISTRATOR_IS_NEVER_KEPT_OUT: Final = (
    "If keeping somebody out would leave no administrator able to sign in, they are kept in and "
    "the run says so, because a directory's word must not lock a company out of its own install "
    "with nobody left to undo it."
)


class KeptOut(enum.StrEnum):
    """Why somebody is kept out. A count of each is reported, never a name."""

    SUSPENDED = "suspended"
    LEFT = "left"
    NOT_ACTIVATED = "not_activated"
    TYPE_NOT_ALLOWED = "type_not_allowed"


#: What a person's page says about why they cannot sign in or ask.
WHY_KEPT_OUT: Final[Mapping[KeptOut, str]] = {
    KeptOut.SUSPENDED: "The staff list says they are suspended, so they cannot sign in or ask.",
    KeptOut.LEFT: "The staff list says they have left, so they cannot sign in or ask.",
    KeptOut.NOT_ACTIVATED: (
        "The staff list says they have never activated their account, so they cannot sign in "
        "or ask."
    ),
    KeptOut.TYPE_NOT_ALLOWED: (
        "Their employment type may not use the Brain on this install, so they cannot sign in or "
        "ask. Settings, under Staff, says which types may."
    ),
}

_COUNTED: Final[Mapping[KeptOut, str]] = {
    KeptOut.SUSPENDED: "suspended",
    KeptOut.LEFT: "gone",
    KeptOut.NOT_ACTIVATED: "never activated",
    KeptOut.TYPE_NOT_ALLOWED: "of a type that may not use the Brain",
}


@dataclass(frozen=True)
class Standing:
    """Where one person on the list stands, keyed elsewhere by their address's digest."""

    status: EmploymentStatus
    employment_type: EmploymentType | None = None


def kept_out_because(standing: Standing, allowed: Collection[EmploymentType]) -> KeptOut | None:
    """Why this standing keeps somebody out, or None when it lets them in."""
    match standing.status:
        case EmploymentStatus.SUSPENDED:
            return KeptOut.SUSPENDED
        case EmploymentStatus.LEFT:
            return KeptOut.LEFT
        case EmploymentStatus.NOT_ACTIVATED:
            return KeptOut.NOT_ACTIVATED
        case EmploymentStatus.ACTIVE:
            pass
    if standing.employment_type is not None and standing.employment_type not in allowed:
        return KeptOut.TYPE_NOT_ALLOWED
    return None


def standings(
    *,
    members: Iterable[StoredMember],
    writes: Iterable[MemberWrite],
    people: Iterable[StaffRecord],
) -> dict[str, Standing]:
    """Where everybody the list can speak for stands, by their address's digest.

    The roster's marks first, then this run's, then the reading itself, each over the last: see the
    module note. Somebody absent from a list that did not promise to be complete is in none of
    them, and nothing is decided about them.
    """
    found: dict[str, Standing] = {}
    for one in members:
        if one.left_at is not None:
            found[one.address_hash] = Standing(EmploymentStatus.LEFT)
    for write in writes:
        if write.write is Write.MARK_LEFT:
            status = (
                write.status
                if write.status is not EmploymentStatus.ACTIVE
                else EmploymentStatus.LEFT
            )
            found[write.address_hash] = Standing(status, write.employment_type)
    for person in people:
        found[digest_of(person.work_address)] = Standing(person.standing, person.employment_type)
    return found


@dataclass(frozen=True)
class Held:
    """A Brain person the list can speak for, as the install holds them."""

    principal_id: str
    disabled: bool
    #: True when the last change to whether they are disabled was this list's sync.
    changed_by_the_list: bool


@dataclass(frozen=True)
class StandingPlan:
    """Whom one run disables and enables, and whom it kept in as the last administrator."""

    to_disable: tuple[tuple[str, KeptOut], ...] = ()
    to_enable: tuple[str, ...] = ()
    kept_in: tuple[str, ...] = ()
    kept_out: Mapping[KeptOut, int] = field(default_factory=dict)

    def sentences(self) -> tuple[str, ...]:
        """What the plan does, in counts."""
        said = [
            f"{self.kept_out[one]} {_COUNTED[one]}" for one in KeptOut if self.kept_out.get(one)
        ]
        found: list[str] = []
        if said or self.to_enable:
            found.append(
                f"Kept out of the Brain: {', '.join(said) if said else 'nobody new'}; "
                f"{len(self.to_enable)} let back in."
            )
        if self.kept_in:
            found.append(
                f"{len(self.kept_in)} kept able to sign in, because keeping them out would leave "
                "no administrator."
            )
        return tuple(found)


def standing_plan(
    standings_by_digest: Mapping[str, Standing],
    *,
    bound: Mapping[str, str],
    held: Mapping[str, Held],
    administrators: Collection[str],
    allowed: Collection[EmploymentType],
) -> StandingPlan:
    """Who is disabled, who enabled, and who kept in, for the people `bound` joins to the list.

    `bound` is an address digest to the principal an email binding names; `held` those principals'
    state; `administrators` the principals who can sign in and administer, as
    `brain.identity.sign_in_binding.SignInBindings.administrators_linked` answers.
    """
    to_disable: list[tuple[str, KeptOut]] = []
    to_enable: list[str] = []
    kept_out: dict[KeptOut, int] = {}
    for digest in sorted(standings_by_digest):
        principal_id = bound.get(digest)
        state = held.get(principal_id) if principal_id is not None else None
        if state is None:
            continue
        why = kept_out_because(standings_by_digest[digest], allowed)
        if why is not None and not state.disabled:
            to_disable.append((state.principal_id, why))
        elif why is None and state.disabled and state.changed_by_the_list:
            to_enable.append(state.principal_id)
    live = {one for one in administrators if one in held and not held[one].disabled} | {
        one for one in administrators if one not in held
    }
    leaving = {pid for pid, _ in to_disable} & live
    kept_in = tuple(sorted(leaving)) if leaving and not live - leaving else ()
    kept = [(pid, why) for pid, why in to_disable if pid not in kept_in]
    for _, why in kept:
        kept_out[why] = kept_out.get(why, 0) + 1
    return StandingPlan(
        to_disable=tuple(sorted(kept)),
        to_enable=tuple(sorted(set(to_enable))),
        kept_in=kept_in,
        kept_out=kept_out,
    )
