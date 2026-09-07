"""Where the staff list comes from, and why not every source may say the same things.

A client keeps their people somewhere already: Google Workspace, Microsoft Entra, Lark, an
LDAP directory, a Google Sheet, or a spreadsheet somebody maintains by hand. The system has to
read from wherever that is, because the alternative is a second staff list that disagrees with
the first inside a month, and the one that is wrong is the one deciding who may see what.

**Two pluggable things, and collapsing them is the mistake this module exists to prevent.**

A *roster source* answers "who works here, in which department, in which groups". It is a
list, it is read on a schedule, and a spreadsheet can be one.

A *sign-in source* answers "prove you are that person". It is a live protocol, and a
spreadsheet can never be one.

Google Workspace, Microsoft and Lark can be both, which is exactly why the two get conflated.
Design for that and the spreadsheet case is impossible, because there is nothing to
authenticate against. So this module governs the roster only. Sign-in stays Keycloak's, where
brokering to Google, Microsoft, Lark or LDAP is configuration rather than code, and the two
are joined by the work address.

**Not every source deserves the same trust, and that is the load-bearing decision here.**

A Google Sheet that anybody in the company can edit is a fine roster and a catastrophic source
of roles: one edit and somebody is a Super Admin. A Google Workspace group is different, since
changing it requires the Workspace admin console and leaves an audit trail there. Both are
legitimate staff sources and they must not be able to assert the same things.

So a source declares what it may assert, `assertions_from` refuses rules that ask it for more,
and the refusal happens when the sync is wired rather than quietly on the night it runs. See
`A_SPREADSHEET_IS_A_ROSTER_AND_NEVER_AN_AUTHORITY`. This is M33.5.4, "set permission-sync
capability per connector", arriving one layer earlier than the connector.

**What a source may never assert, whatever its trust.** No capability, ever. A group maps to a
`Role` and to nothing else, which is `brain.identity.directory`'s rule and the reason it gives:
the alternative moves "who can see the margin on this client" into a directory nobody in this
company reviews. There is no trust level here that unlocks capabilities, because there is no
member for one.

**Absence is not deletion.** A person missing from today's roster is a person the source did
not mention, which is not the same as a person who left: an export that half-failed, a filter
somebody changed, or a paging bug all produce the same silence. `roster_is_complete` is the
declaration a source makes about whether its answer is the whole list, and a source that
cannot promise that can add and can never remove. `brain.identity.directory.reconcile` does
the removing and is handed only what a complete source produced.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from brain.identity.directory import DirectoryAssertion
from brain.identity.roles import Role

#: Why a source that anybody can edit may list people and may not appoint them.
A_SPREADSHEET_IS_A_ROSTER_AND_NEVER_AN_AUTHORITY: Final = (
    "A Google Sheet that anybody in the company can edit is a perfectly good answer to who "
    "works here and a catastrophic answer to who is a Super Admin: one edit to a cell and "
    "somebody has appointed themselves, with the edit history in a document nobody reviews. "
    "A Workspace group is a different thing, because changing it needs the admin console and "
    "leaves a trail there. Both are legitimate rosters. They must not be able to assert the "
    "same facts, and the refusal has to happen when the sync is wired rather than on the "
    "night it runs."
)

#: Why a missing person is not a departed person.
A_SOURCE_THAT_HALF_ANSWERED_LOOKS_EXACTLY_LIKE_A_COMPANY_THAT_HALVED: Final = (
    "An export that timed out, a filter somebody narrowed and a paging bug all produce the "
    "same thing: a shorter list. Treating absence as departure turns any of them into a mass "
    "revocation that looks, in the audit ledger, exactly like a deliberate one. A source "
    "therefore declares whether its answer is the whole list, and one that cannot promise "
    "that may add and may never remove."
)

#: Why sign-in is not this module's problem.
A_SPREADSHEET_CANNOT_BE_AUTHENTICATED_AGAINST: Final = (
    "A roster is a list read on a schedule; a sign-in source is a live protocol that proves "
    "somebody is who they say. Google, Microsoft and Lark can be both, which is why the two "
    "get conflated, and designing for that makes the spreadsheet case impossible because "
    "there is nothing to authenticate against. Sign-in stays with Keycloak, where brokering "
    "to any of them is configuration rather than code, and the two are joined by the work "
    "address."
)


class Asserts(enum.StrEnum):
    """What a roster source is trusted to say. Three members and deliberately no fourth.

    There is no member for a capability, and that is the point rather than an omission. A
    group maps to a role and never to a capability, because a capability in a directory moves
    "who can see the margin" out of this system and into one nobody here reviews. A fourth
    member is how that arrives.
    """

    #: This person works here, and this is their name and work address.
    EXISTENCE = "existence"
    #: This person is in this department, which is the scope their grants are bounded by.
    DEPARTMENT = "department"
    #: This person holds this platform role: approver, auditor, department admin.
    ROLE = "role"


#: What each kind of source may be trusted with, before anybody configures anything.
#:
#: A default rather than a fixed rule: an installation whose sheet is locked to two people may
#: raise it, and one whose Workspace groups are edited by a helpdesk may lower it. What it
#: cannot do is start permissive, which is why a source with no entry here asserts existence
#: alone.
DEFAULT_TRUST: Final[dict[str, frozenset[Asserts]]] = {
    # Editable by whoever holds the link. A list of people and nothing more.
    "spreadsheet": frozenset({Asserts.EXISTENCE}),
    "google_sheet": frozenset({Asserts.EXISTENCE}),
    # Changing these needs an admin console and leaves a trail in it.
    "google_workspace": frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
    "microsoft_entra": frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
    "lark": frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
    "ldap": frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
    # Keycloak's own groups, for an installation with no directory behind it.
    "keycloak": frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
}

#: What a source asserts when nobody has said. Existence and nothing else.
LEAST_TRUST: Final[frozenset[Asserts]] = frozenset({Asserts.EXISTENCE})


class StaffSourceError(Exception):
    """Raised when a roster source is asked for something it is not trusted to say."""


@dataclass(frozen=True)
class StaffRecord:
    """One person, as one roster source describes them.

    `work_address` rather than an identifier of the source's own, because it is the join to
    the sign-in identity and the only field every one of these systems has in common. It is
    also the field that changes when somebody marries or the company rebrands its domain,
    which is the migration this design will one day have to handle and does not yet.
    """

    work_address: str
    display_name: str
    #: The department the source places them in, when it is trusted to say. Empty otherwise.
    department: str = ""
    #: Group names as the source spells them, before any mapping to a role.
    groups: tuple[str, ...] = ()
    #: False when the source says this person has left. Distinct from being absent entirely.
    active: bool = True

    def __post_init__(self) -> None:
        if "@" not in self.work_address or not self.work_address.strip():
            msg = (
                f"{self.work_address!r} is not a work address, and the address is the only "
                "join between a roster entry and the person who signs in"
            )
            raise ValueError(msg)
        if not self.display_name.strip():
            msg = f"{self.work_address} has no display name, so no screen can name them"
            raise ValueError(msg)


@dataclass(frozen=True)
class Roster:
    """One source's answer, and whether it is the whole answer.

    `complete` is the field that decides whether anybody may be removed on the strength of
    this. See `A_SOURCE_THAT_HALF_ANSWERED_LOOKS_EXACTLY_LIKE_A_COMPANY_THAT_HALVED`.
    """

    source: str
    people: tuple[StaffRecord, ...]
    #: True only when the source can say this is every person, not merely every person it
    #: managed to fetch. A paged API that stopped early must set this False.
    complete: bool
    asserts: frozenset[Asserts] = field(default_factory=lambda: LEAST_TRUST)

    def __post_init__(self) -> None:
        if not self.source.strip():
            msg = "a roster with no source cannot be reconciled against its own previous run"
            raise ValueError(msg)
        seen = [one.work_address.casefold() for one in self.people]
        repeated = sorted({one for one in seen if seen.count(one) > 1})
        if repeated:
            msg = (
                f"{self.source} lists {repeated} more than once; two rows for one person "
                "make every set difference below ambiguous"
            )
            raise ValueError(msg)

    def may_remove(self) -> bool:
        """Whether anything may be deleted on the strength of this run."""
        return self.complete


class StaffSource(Protocol):
    """Whatever can produce a roster. Read on a schedule, never at sign-in.

    A protocol rather than a base class, so a client's own script that writes a CSV is as
    much a staff source as a Workspace connector, and neither has to import anything of ours
    to be one.
    """

    def roster(self) -> Roster: ...


def trust_for(source: str, configured: frozenset[Asserts] | None = None) -> frozenset[Asserts]:
    """What this source may assert, from configuration or from the cautious default.

    An unknown source gets `LEAST_TRUST` rather than an error, because a client naming their
    own export script should not have to add a line to this file, and the safe answer for
    something nobody has assessed is that it may list people and nothing more.
    """
    if configured is not None:
        return configured
    return DEFAULT_TRUST.get(source, LEAST_TRUST)


@dataclass(frozen=True)
class GroupRule:
    """One mapping from a group name a source uses to a role this platform knows.

    Held here rather than inferred, because a group called `admins` means different things in
    two companies and neither of them is necessarily this system's Super Admin.
    """

    source_group: str
    role: Role


def assertions_from(
    roster: Roster,
    rules: Sequence[GroupRule],
    *,
    principal_for: dict[str, str],
) -> tuple[DirectoryAssertion, ...]:
    """The role assertions this roster supports, refusing any the source may not make.

    **Refuses rather than filters.** A source configured with role rules it is not trusted to
    assert is a misconfiguration, and silently dropping those rules would leave somebody
    looking at a rule that does nothing and an audit trail that says nothing happened. The
    error names the source and the rules, so the person who wired it can see what they asked
    for.

    `principal_for` maps a work address to the principal this system already knows. An address
    with no principal is skipped rather than invented: creating a principal is provisioning,
    which is `brain.identity.lifecycle.provision`'s job and carries decisions this function has
    no business making.
    """
    if rules and Asserts.ROLE not in roster.asserts:
        named = sorted({one.source_group for one in rules})
        msg = (
            f"{roster.source!r} is trusted with {sorted(roster.asserts)} and has been given "
            f"role rules for {named}. A source that may not assert roles must not be wired to "
            "any, because a rule that is quietly ignored looks exactly like a rule that is "
            "working"
        )
        raise StaffSourceError(msg)

    by_group = {one.source_group: one.role for one in rules}
    found: list[DirectoryAssertion] = []
    for person in roster.people:
        principal = principal_for.get(person.work_address.casefold())
        if principal is None or not person.active:
            continue
        for group in person.groups:
            role = by_group.get(group)
            if role is not None:
                found.append(
                    DirectoryAssertion(principal_id=principal, role=role, source_group=group)
                )
    return tuple(
        sorted(found, key=lambda one: (one.principal_id, one.role.value, one.source_group))
    )


def departments_from(roster: Roster) -> dict[str, str]:
    """Work address to department, for the sources trusted to say.

    Empty for a source that is not, rather than a partial map somebody would have to know to
    distrust. A caller that wanted departments and got none can look at the trust and see why.
    """
    if Asserts.DEPARTMENT not in roster.asserts:
        return {}
    return {one.work_address.casefold(): one.department for one in roster.people if one.department}


def source_gaps(rosters: Iterable[Roster]) -> tuple[str, ...]:
    """Everything about a set of configured sources that would produce a wrong answer.

    Three checks, and the third is the one nobody thinks of: two sources both trusted to
    assert roles will fight, because each reconciles its own table and neither can see the
    other's rows. That is survivable and it must be deliberate.
    """
    found: list[str] = []
    seen = list(rosters)

    for one in seen:
        if not one.complete and one.people:
            found.append(
                f"{one.source!r} did not promise a complete list, so nobody may be removed "
                "on the strength of this run; additions are safe and deletions are not"
            )
        if Asserts.EXISTENCE not in one.asserts:
            found.append(
                f"{one.source!r} is not trusted to say who exists, which is the one thing "
                "every roster source is for"
            )

    authorities = [one.source for one in seen if Asserts.ROLE in one.asserts]
    if len(authorities) > 1:
        found.append(
            f"{sorted(authorities)} are all trusted to assert roles; each reconciles its own "
            "rows and none can see the others', so a person removed from a group in one "
            "keeps the role if another still asserts it. That is the additive rule working "
            "as designed and it is rarely what somebody configuring a second source expects"
        )

    return tuple(found)
