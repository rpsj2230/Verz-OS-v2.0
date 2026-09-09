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
`A_SPREADSHEET_IS_A_ROSTER_AND_NEVER_AN_AUTHORITY`. It is the same decision M33.5.1.3 asks
for per connector, "set permission-sync capability per connector", arriving one layer earlier
and so not claimed here: that leaf is about a connector's credential custody and this is about
a roster's trust. The id in this paragraph read `M33.5.4` until 2026-09-07, which is not a leaf
in this tree at all, because task ids under M33 are four levels deep.

**Which of these a company uses is not a fact this repository can hold.** This is the master a
client's install is made from, so there is no staff list here to name: one company keeps its
people in a sheet, the next in a directory, the one after in an export somebody wrote. So the
set of sources is data, `SELECTABLE`, and the choice is one installation setting read through
`brain.install.value_of`, which is the one place a client value is read. Three refusals follow
and every one of them is a shape that would otherwise be silent.

*A name nobody recognises is refused, and the refusal lists what is available.* The tempting
alternative is a fallback to a default, and the install it would fall back on is the one whose
operator misspelled a word. There is no default source at all, for the same reason: whichever
one happened to be written first would become every client's.
See `ONE_COMPANYS_ARRANGEMENT_IS_NOT_EVERY_COMPANYS`.

*A source chosen and pointed nowhere is refused, naming the settings nobody supplied.* A
directory with no address answers with nothing, a sheet with no identifier answers with
nothing, and nothing is exactly what a company where everybody left looks like, because
`brain.identity.staff_sync` reads what a source returns as the membership. That is also why
`roster_from` refuses a roster of nobody rather than handing it on.
See `A_SOURCE_NOBODY_POINTED_ANYWHERE_ANSWERS_WITH_AN_EMPTY_COMPANY`.

*Choosing a staff list may not raise what it is trusted to assert.* `SelectableSource` carries
no trust and there is no setting for one, so `trust_for` stays the only answer to what a source
may say and this adds no second one: `roster_from` calls it and refuses a roster claiming more.
`docs/needs-rupash.md` item 39 asked whether the staff list may set roles and the answer was
no, the staff list lists people and roles are set in the console, so an environment file is not
somewhere anybody can be appointed from.
See `CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY`.

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

Task ids: M1.6.1, M1.6.2, M1.6.3, M1.6.7, M1.6.9, M1.6.10
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from brain.identity.directory import DirectoryAssertion
from brain.identity.roles import Role
from brain.install import BY_NAME, value_of

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

#: Why there is no default staff source and an unrecognised name is a refusal.
ONE_COMPANYS_ARRANGEMENT_IS_NOT_EVERY_COMPANYS: Final = (
    "This repository is the master a client's install is made from, and there is no staff "
    "list in it to name: one company keeps its people in a sheet, the next in a directory, "
    "the one after in an export somebody wrote. A default source would make whichever one was "
    "written first every client's, and an unrecognised name quietly falling back to it would "
    "do the same on the install whose operator misspelled a word. So the set of sources is "
    "data, the choice is one setting, and a name outside the set is refused with the set."
)

#: Why a source nobody pointed anywhere refuses rather than answering.
A_SOURCE_NOBODY_POINTED_ANYWHERE_ANSWERS_WITH_AN_EMPTY_COMPANY: Final = (
    "A directory with no address, a sheet with no identifier and a credential nobody supplied "
    "all answer the same way, and the answer parses: nobody. That is not a company with no "
    "staff, it is a source that was never wired, and the sync cannot tell the difference "
    "because it reads what a source returns as the membership. So a chosen source with a "
    "setting unsupplied refuses and names the setting, and a roster of nobody refuses at the "
    "point it arrives rather than being carried to the diff that would propose emptying the "
    "company."
)

#: Why choosing a staff list is not a way to appoint anybody.
CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY: Final = (
    "An install picks which staff list this company keeps its people in. It does not get to "
    "pick what that list is believed about them: `trust_for` is the one answer to that, and a "
    "second one written into the selection would let an environment file hand a shared "
    "spreadsheet the power to name a Super Admin. Item 39 asked the question and the answer "
    "was that the staff list lists people and roles are set in the console, so a roster "
    "arriving through the selection saying more than its source is trusted with is refused "
    "rather than trimmed: a widening somebody configured and cannot see is the whole failure."
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


# ---------------------------------------------------- choosing one of them at install time
#: The setting naming which of `SELECTABLE` this install reads its staff list from.
STAFF_SOURCE_SETTING: Final = "INSTALL_STAFF_SOURCE"

#: The setting naming where that list is: which sheet, which tenant, which directory.
STAFF_SOURCE_LOCATION_SETTING: Final = "INSTALL_STAFF_SOURCE_LOCATION"


@dataclass(frozen=True)
class SelectableSource:
    """One answer a client's install may give to where they keep their staff list.

    **It carries no trust and there is deliberately no field for one.** What a source may
    assert is `trust_for`, and a copy of that answer here would be a second one reachable from
    an environment file, which is `CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY`. Choosing a
    source says where the list is read from and nothing about what it is believed about.

    `needs` names installation settings rather than describing them, so a source that cannot be
    pointed anywhere is a refusal naming a variable somebody can set rather than a sentence
    they have to translate into one. Every name in it is checked against the declaration in
    `brain.install` at import, because a requirement naming a setting nobody declared can never
    be satisfied and would make that source permanently unselectable on every install.
    """

    #: The value `INSTALL_STAFF_SOURCE` is set to, and the `Roster.source` the adapter pins.
    name: str
    #: What choosing it means, for whoever is choosing on install day.
    meaning: str
    #: The installation settings that must carry a value before this source can be read.
    needs: tuple[str, ...] = ()
    #: False for the one option that reads no list at all.
    reads_a_list: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.meaning.strip():
            msg = (
                f"{self.name!r} is not a staff source somebody could choose: a name and a "
                "meaning are what a setup screen shows and what a refusal lists"
            )
            raise ValueError(msg)
        if self.reads_a_list and self.name not in DEFAULT_TRUST:
            msg = (
                f"{self.name!r} is offered as a staff source and the trust table has no entry "
                "for it, so an install choosing it gets LEAST_TRUST with nothing saying so. "
                "See A_SPREADSHEET_IS_A_ROSTER_AND_NEVER_AN_AUTHORITY for what that table is"
            )
            raise ValueError(msg)
        if not self.reads_a_list and self.needs:
            msg = (
                f"{self.name!r} reads no list and requires {sorted(self.needs)}, which is a "
                "setting an install can never satisfy its way out of needing"
            )
            raise ValueError(msg)
        undeclared = sorted(one for one in self.needs if one not in BY_NAME)
        if undeclared:
            msg = (
                f"{self.name!r} needs {undeclared}, which brain.install does not declare, so "
                "there is nowhere to set them and this source refuses on every install"
            )
            raise ValueError(msg)

    def unsupplied(self, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        """The settings this source needs that this installation has left at their default.

        Compared against the declared default rather than against emptiness, because
        `brain.install.Setting` refuses an optional setting with an empty default for exactly
        this reason: an unset value and a value set to nothing would otherwise be the same
        thing and neither would be reported. The cost is that an install whose sheet really is
        identified by the neutral word reads as unset, which is a sentence in a runbook rather
        than a failure anybody meets.
        """
        return tuple(one for one in self.needs if value_of(one, env) == BY_NAME[one].default)


#: Every value `INSTALL_STAFF_SOURCE` may take, and what each one means to whoever picks it.
#:
#: Data rather than a branch, so a client's install chooses by name and a seventh source is a
#: row here plus an adapter rather than an edit to a function nobody reads. The order is the
#: order a refusal lists them in, and `none` is first because it is what an install that has
#: not chosen has: the absence of a source rather than one of them picked on its behalf.
SELECTABLE: Final[tuple[SelectableSource, ...]] = (
    SelectableSource(
        name="none",
        meaning=(
            "No staff list is read. People are created in the console by hand, which is the "
            "right answer for a company small enough to do it and the only honest default: a "
            "product that guessed would be guessing at who works somewhere it has never seen."
        ),
        reads_a_list=False,
    ),
    SelectableSource(
        name="spreadsheet",
        meaning=(
            "A staff list somebody keeps by hand, uploaded as rows. Nothing to point at, "
            "because the file is the answer. It may say who works here and never who holds a "
            "role, and it can never promise to be the whole list."
        ),
    ),
    SelectableSource(
        name="google_sheet",
        meaning=(
            "The same list kept in a Google Sheet and read through the Sheets API, which can "
            "say whether the read finished inside the range it asked for. Existence only, for "
            "the same reason as the file above: anybody with the link edits it."
        ),
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
    ),
    SelectableSource(
        name="google_workspace",
        meaning=(
            "Google Workspace's own directory, where changing a group needs the admin console "
            "and leaves a trail in it. Trusted with departments and roles by default."
        ),
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
    ),
    SelectableSource(
        name="microsoft_entra",
        meaning=(
            "Microsoft Entra, read through Graph. The join is the sign-in name rather than "
            "the mail address, which is why the tenant has to be named."
        ),
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
    ),
    SelectableSource(
        name="lark",
        meaning=(
            "Lark's contact directory, with departments read by name rather than by their "
            "opaque identifiers."
        ),
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
    ),
    SelectableSource(
        name="ldap",
        meaning=(
            "An LDAP directory or Active Directory. One value points at it, because an LDAP "
            "address carries the base it is searched from and two settings that can disagree "
            "about where a search starts is a roster that is silently about a sub-tree."
        ),
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
    ),
)

#: The same, indexed. A choice is looked up on the read path of a scheduled sync.
SELECTABLE_BY_NAME: Final[dict[str, SelectableSource]] = {one.name: one for one in SELECTABLE}


def selectable_names() -> tuple[str, ...]:
    """Every name an install may choose, in the order a refusal lists them."""
    return tuple(one.name for one in SELECTABLE)


def selected_source(
    env: Mapping[str, str] | None = None, *, sources: Sequence[SelectableSource] = SELECTABLE
) -> SelectableSource:
    """Which staff list this installation reads, refusing rather than choosing one for it.

    Two refusals, and neither of them has a fallback. An unrecognised name is refused with the
    names that exist rather than resolved to a default, because the install that would meet
    that default is the one whose operator mistyped, and the symptom would be a roster read
    from somewhere nobody chose. A recognised name whose settings are unsupplied is refused
    naming them, because the source would otherwise be read, would answer with nobody, and
    nobody is what a company where everybody left looks like.

    **`sources` is a parameter and a mutation is why.** It read the module's tuple directly,
    and every source declared there needs at most one setting, so the half of the refusal that
    names several was unreachable: dropping all but the first survived. That is not the case
    being impossible, it is the case being unbuildable from outside, which is exactly the
    argument `brain.ops.starter.starter_gaps` makes about its own parameters. A source needing
    an address and a credential is the obvious next one to add.

    The default is the real tuple, so calling it with no arguments is the deployment question
    and calling it with a constructed set is the test.

    See `ONE_COMPANYS_ARRANGEMENT_IS_NOT_EVERY_COMPANYS` and
    `A_SOURCE_NOBODY_POINTED_ANYWHERE_ANSWERS_WITH_AN_EMPTY_COMPANY`.
    """
    # No second `.strip()` here, and a mutation is why: `brain.install.value_of` strips
    # what it reads before returning it, so one here could be removed with nothing
    # failing. A guard that cannot fire is this repository's most common defect, and one
    # sitting on the boundary between two modules is the version that reads as belt and
    # braces while being neither. The property is pinned by a test one module over.
    chosen = value_of(STAFF_SOURCE_SETTING, env)
    found = {one.name: one for one in sources}.get(chosen)
    if found is None:
        msg = (
            f"{chosen!r} is not a staff list this product can read. {STAFF_SOURCE_SETTING} "
            f"takes one of {[one.name for one in sources]}, and there is no default: a name "
            f"that "
            "fell back to one would read this company's people out of somewhere nobody chose"
        )
        raise StaffSourceError(msg)
    unsupplied = found.unsupplied(env)
    if unsupplied:
        msg = (
            f"{found.name!r} is the chosen staff list and {list(unsupplied)} "
            f"{'is' if len(unsupplied) == 1 else 'are'} unset, so there is nothing to read it "
            "from. A source nobody pointed anywhere answers with nobody, and nobody is what a "
            "company everybody left looks like to a sync"
        )
        raise StaffSourceError(msg)
    return found


def roster_from(source: StaffSource, chosen: SelectableSource) -> Roster:
    """The chosen source's roster, refusing the three answers a sync must never be handed.

    The seam between "which source this install reads" and "what that source said", and the
    only place the two are checked against each other. **Nothing in the product calls it yet**,
    and that is worth saying plainly rather than leaving a reader to infer it is on a live
    path: the console page that lets somebody choose a source and test it before it runs is the
    caller this was written for, and the scheduled sync is the second. Until one of them exists
    an install can name its staff source and nothing reads it.

    **The widening check calls `trust_for` rather than restating it.** A roster may say less
    than its source's declared trust, because an installation lowering a source is a real
    configuration this module has always supported. It may not say more through a choice made
    in an environment file, which is `CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY`.

    **A roster of nobody is refused here rather than reported later.** `source_gaps` says
    nothing about an empty roster on purpose, because "nobody may be removed" is not a useful
    sentence about one, and `brain.identity.staff_sync.dry_run` would carry a complete empty
    one to a diff proposing that every person in the company be removed. The refusal is at the
    point the answer arrives, where the source that produced it is still in hand.
    """
    if not chosen.reads_a_list:
        msg = (
            f"{chosen.name!r} reads no staff list, so there is no roster to ask it for. An "
            "install with no source provisions people in the console, and an empty answer "
            "from here would be a proposal to remove everybody it has"
        )
        raise StaffSourceError(msg)

    roster = source.roster()
    if roster.source != chosen.name:
        msg = (
            f"this install reads {chosen.name!r} and was handed a roster from "
            f"{roster.source!r}. Reconciliation compares a source's rows against that same "
            "source's previous rows, so the two would delete each other's assertions on "
            "every run"
        )
        raise StaffSourceError(msg)

    widened = sorted(roster.asserts - trust_for(chosen.name))
    if widened:
        msg = (
            f"{roster.source!r} was read through the install's own choice and claims "
            f"{widened}, which is more than that source is trusted with. Choosing where a "
            "staff list lives is not appointing anybody from it"
        )
        raise StaffSourceError(msg)

    if not roster.people:
        msg = (
            f"{roster.source!r} answered with nobody. A company running this system has "
            "somebody in it, so this is a source pointed at the wrong place or one that could "
            "not read, and both of those look exactly like every person having left"
        )
        raise StaffSourceError(msg)
    return roster


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
