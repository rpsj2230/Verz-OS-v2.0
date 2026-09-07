"""What it means when somebody's work address changes, and why that is not one question.

`StaffRecord` keeps the work address rather than an identifier of the source's own, because
it is the join between a roster entry and the person who signs in and the only field every
one of these systems has in common. Its docstring then names the consequence and leaves it:
the address "is also the field that changes when somebody marries or the company rebrands its
domain, which is the migration this design will one day have to handle and does not yet".
This module is that migration.

**A roster diff cannot tell a rename from a departure and an arrival, and nothing makes it
able to.** Compare Monday's addresses with Tuesday's and a person who married is a person who
left and a stranger who joined. The two are the same two set differences. Worse, they are the
same two set differences as a paging bug, and `staff_source` already says what that costs in
`A_SOURCE_THAT_HALF_ANSWERED_LOOKS_EXACTLY_LIKE_A_COMPANY_THAT_HALVED`.
So the diff is not where the answer is.

**The decision: a changed address is a different person unless the source carried something
stable that says otherwise.** Not the display name, not a fuzzy match on the local part, not
the department they are in. An identifier the source issues and does not reissue, or nothing.
The reason is not tidiness, it is that the alternative is an account takeover with no
exploit in it: on a source where a matching display name is enough, anybody who can edit the
roster types a colleague's name beside their own address and inherits that colleague's
principal, their grants and their department. A spreadsheet is exactly such a source, which
is why this rule and the trust rule land in the same place from different directions.

**So a rename is recognisable on a directory and is not recognisable on a spreadsheet**, and
that is the honest answer rather than a limitation to be worked around. Every directory here
issues one: Google's `id`, Entra's object id, Lark's `union_id`, `objectGUID` or `entryUUID`
in a directory. A hand-kept sheet issues nothing, so on a hand-kept sheet a changed address is
an arrival, and on an incomplete one it is only an arrival, because the old row's absence is
not a departure. The person keeps two entries until somebody says otherwise, which is
untidy and is not dangerous. `THE_ONLY_SAFE_DEFAULT_IS_TWO_PEOPLE` is that argument.

**The new address already belonging to somebody else is the case that must not be automated.**
Two shapes, and both end at a person rather than at a rule:

- *A reissue.* Somebody left, the company handed their address to a new joiner, and the new
  joiner's stable identifier now sits at an address whose previous holder is still bound to a
  principal here. Applying the rename gives the new holder the old holder's grants. This is
  not exotic: reissuing `info@`, a departed salesperson's address or a common first name is
  ordinary practice, and the whole point of the reissue is that mail keeps working.
- *A swap.* Two people exchange addresses, which happens when a mistake made at onboarding is
  corrected. Both changes are renames and applying either one alone binds one person's
  address to the other for as long as it takes to apply the second.

Both are reported and neither is applied. See `A_REISSUED_ADDRESS_INHERITS_WHOEVER_HELD_IT`.

**Absence is still not deletion, and a rename is not deletion either.** A stable identifier
that is missing from this reading is a departure only when the roster promised completeness,
which is read off the roster rather than passed in, for the same reason the adapters derive it
rather than accept it: the promise decides whether anybody may be removed and a caller in a
hurry is who would make it.

**Nothing here rebinds anything.** It returns what changed and what a person has to look at,
in the shape `brain.identity.directory.reconcile` already uses for the same reason: the
function that decides is pure and testable without a database, and the function that writes
holds a transaction and no judgement. The rebind itself is `auth.principal_identity`'s and it
is not built here.

Task ids: M1.6.8
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.identity.staff_source import Roster

# ------------------------------------------------------------------ written-down reasons
#: Why the two things a changed address might be cannot be told apart from the diff alone.
A_RENAME_AND_A_DEPARTURE_ARE_THE_SAME_TWO_SET_DIFFERENCES: Final = (
    "Monday's addresses against Tuesday's give one address gone and one address new, and "
    "that is what a marriage looks like, what a resignation and a hire look like, and what a "
    "paging bug looks like. Nothing in the difference distinguishes them, so the answer "
    "cannot come from the difference. It comes from whether the source carried an identifier "
    "that survived the change, and a source that carried none has not said anything about "
    "which of the three happened."
)

#: Why a display name is not evidence and no function here may take one.
A_DISPLAY_NAME_IS_NOT_EVIDENCE_OF_IDENTITY: Final = (
    "Matching a changed address to a person by their name is an account takeover with no "
    "exploit in it: on any source somebody can edit, they type a colleague's name beside "
    "their own address and inherit that colleague's principal, grants and department. It is "
    "also wrong in the ordinary case, because a name is exactly what changes when somebody "
    "marries and the address is what stays. There is no parameter anywhere in this module "
    "that a display name fits into, which is a property a reviewer can check by reading the "
    "signatures rather than a rule somebody has to remember."
)

#: Why an unrecognisable change leaves two entries rather than guessing at one.
THE_ONLY_SAFE_DEFAULT_IS_TWO_PEOPLE: Final = (
    "When nothing says a changed address is the same person, the safe reading is that it is "
    "two people: one who has arrived and one who may or may not have gone. That leaves a "
    "duplicate for somebody to merge, which is untidy and visible. Guessing the other way "
    "moves a live sign-in join onto an address on the strength of a similarity, and the "
    "failure is silent and is somebody holding what another person held."
)

#: Why an address that has changed hands is never applied without a person looking.
A_REISSUED_ADDRESS_INHERITS_WHOEVER_HELD_IT: Final = (
    "An address is the join to a sign-in identity, so binding a new person to an address the "
    "system already knows hands them whatever the previous holder had. Companies reissue "
    "addresses on purpose and the purpose is that mail keeps working. The stable identifier "
    "is right that this is a different person from the one at that address before, and that "
    "is precisely the reason not to complete the join automatically: the identifier says the "
    "holder changed, and the grants attached to the address did not change with it."
)

#: Why two addresses for one identifier stops the reading rather than picking one.
ONE_IDENTIFIER_AT_TWO_ADDRESSES_MAKES_EVERY_MATCH_BELOW_AMBIGUOUS: Final = (
    "A reading that says one person is at two addresses at once cannot answer which of them "
    "they moved to, and every comparison after that point inherits the ambiguity. `Roster` "
    "refuses the mirror image of this at construction, where one address names two people, "
    "and for the same reason: two rows for one person make every set difference below them "
    "ambiguous. Refused rather than resolved, because there is no answer to choose."
)


class AddressError(Exception):
    """A reading of a source's addresses that cannot be compared with another."""


@dataclass(frozen=True)
class AddressChange:
    """One identifier that moved from one address to another, and what corroborates it.

    Frozen and ordered by the identifier, so two runs over the same pair of readings produce
    equal results. That matters for the same reason it matters in
    `brain.identity.directory.DirectoryAssertion`: a caller diffing two runs of this would
    otherwise see churn that is an artefact of set iteration order.
    """

    #: The identifier the source issues, which is what makes this a move rather than a
    #: coincidence. Never the address, and never anything derived from a person's name.
    stable_id: str
    was: str
    now: str
    #: True when the source still lists the old address as one of this person's own: a
    #: Workspace alias, an Entra lower-case `smtp:` proxy address.
    #:
    #: One field rather than two, and it is worth saying why, because it answers two
    #: questions and an earlier draft had a field for each with one computation behind them.
    #: It corroborates the move, since an alias list is evidence independent of the
    #: identifier; and it says the old address cannot be handed to anybody else tomorrow,
    #: since the source is still holding it. False is not a doubt about the rename. Lark and
    #: an LDAP directory publish no such list at all, and requiring one would make every
    #: rename on those sources unrecognisable. What False does mean is that the old address
    #: is free, which is what makes rebinding promptly a safety measure rather than tidiness.
    old_address_retained: bool = False


@dataclass(frozen=True)
class Reissue:
    """An address that has changed hands, which no rule here may complete on its own.

    The previous holder is named by their identifier rather than by their address, because
    the address is the thing under dispute and naming a person by it is what produced the
    dispute.
    """

    address: str
    #: Who holds it in this reading.
    now_held_by: str
    #: Who held it in the previous reading.
    was_held_by: str
    #: True when the previous holder is still in this reading under some other address, which
    #: makes this half of a swap: applying either half alone binds one person's address to
    #: the other until the second half lands.
    previous_holder_still_here: bool


@dataclass(frozen=True)
class AddressReading:
    """What changed between two readings of one source, and what a person has to look at.

    Returned rather than executed, and it carries no verbs. Nothing here rebinds a sign-in
    identity, creates a principal or deletes one: `brain.identity.lifecycle.provision` owns
    the first arrival and `auth.principal_identity` owns the join, and a function that both
    decided and wrote would be one whose dangerous half only runs against a real table.
    """

    source: str
    #: Moves that are safe to apply: an identifier that changed address, where the new
    #: address was not somebody else's.
    renamed: tuple[AddressChange, ...]
    #: Addresses that changed hands. Never in `renamed`, and never applied automatically.
    reissued: tuple[Reissue, ...]
    #: Identifiers seen for the first time. Provisioning, which belongs elsewhere.
    arrived: tuple[str, ...]
    #: Identifiers that were here and are not now. Empty unless the roster promised
    #: completeness, because absence is not deletion.
    departed: tuple[str, ...]
    #: Addresses in this roster the source gave an identifier for. A change to one of these
    #: can be recognised as a move.
    identified: tuple[str, ...]
    #: Addresses in this roster that the source gave no identifier for. A change to one of
    #: these is unrecognisable, so it reads as an arrival and never as a rename. Together
    #: with `identified` this is every address in the roster and nothing else.
    unidentified: tuple[str, ...]

    @property
    def renames_are_recognisable(self) -> bool:
        """Whether this source issued an identifier for anybody in this roster.

        False for a spreadsheet, and a caller that gets False has been told something
        important: on this source every changed address is a new person, so a marriage
        produces a duplicate that somebody merges by hand. There is no configuration that
        changes it, because the missing thing is in the source rather than here.

        Read off the identifiers rather than off whether anything changed. A directory on a
        quiet week changes nothing, and answering False for it would say the source cannot
        recognise a rename when what happened is that nobody had one.
        """
        return bool(self.identified)

    @property
    def needs_a_person(self) -> tuple[Reissue, ...]:
        """Everything a rule must not decide. Today that is exactly the reissues."""
        return self.reissued


def _folded(pairs: Mapping[str, str], which: str) -> dict[str, str]:
    """Addresses folded, refusing two spellings of one address that name different people.

    Folded because a directory exporting one address in two capitalisations is a directory
    rather than a hypothetical, and `Roster` folds for the same reason when it checks for a
    person listed twice. Refused rather than folded quietly because a dict comprehension over
    a collision keeps whichever came last, and which of two people an address belongs to is
    not a question to answer by iteration order.
    """
    found: dict[str, str] = {}
    for address, identifier in pairs.items():
        folded = address.strip().casefold()
        if folded in found and found[folded] != identifier:
            msg = (
                f"the {which} reading spells {folded!r} two ways and gives the two spellings "
                "different people, so there is no answer to who is at that address"
            )
            raise AddressError(msg)
        found[folded] = identifier
    return found


def _by_identifier(pairs: Mapping[str, str], which: str) -> dict[str, str]:
    """Identifier to address, refusing an identifier that sits at two addresses at once.

    See `ONE_IDENTIFIER_AT_TWO_ADDRESSES_MAKES_EVERY_MATCH_BELOW_AMBIGUOUS`.
    """
    found: dict[str, str] = {}
    doubled: list[str] = []
    for address, identifier in pairs.items():
        if identifier in found:
            doubled.append(identifier)
            continue
        found[identifier] = address
    if doubled:
        msg = (
            f"the {which} reading puts {sorted(set(doubled))} at more than one address at "
            "once, so nothing below can say which address they moved to"
        )
        raise AddressError(msg)
    return found


def address_changes(
    *,
    roster: Roster,
    previous: Mapping[str, str],
    current: Mapping[str, str],
    retained: Mapping[str, Sequence[str]] | None = None,
) -> AddressReading:
    """What changed between two readings of one source's addresses.

    `previous` and `current` map a work address to the identifier the source issues for the
    person at it, which is what `staff_adapters.RosterReading.stable_ids` produces. `retained`
    is the other addresses the source still lists as somebody's own, which corroborates a move
    and never establishes one.

    **Completeness is read off the roster and is not a parameter.** It decides whether a
    missing identifier is a departure, which is the one thing in this answer that removes
    something, and a caller able to pass it is a caller able to promise on the source's
    behalf. The adapters derive it from the payload for the same reason.

    **There is no parameter here that a display name fits into**, and that is the enforcement
    of `A_DISPLAY_NAME_IS_NOT_EVIDENCE_OF_IDENTITY` rather than a note about it. A future
    author who wants to match on a name has to change the signature first, which is a diff
    with a reviewer on it.

    Rejected: matching an unidentified address by its local part, so `a.smith@old.example` and
    `a.smith@new.example` join across a domain rebrand. It is the case people ask for first
    and it is the same takeover as the name match, one field along: on a source somebody can
    edit, choosing your own local part chooses whose principal you inherit. A domain rebrand
    is a migration somebody runs deliberately with a mapping in front of them, and a mapping
    is what `previous` is.
    """
    was = _folded(previous, "previous")
    now = _folded(current, "current")
    still_held = {
        address.strip().casefold(): {one.strip().casefold() for one in others}
        for address, others in (retained or {}).items()
    }

    where_was = _by_identifier(was, "previous")
    where_now = _by_identifier(now, "current")

    renamed: list[AddressChange] = []
    reissued: list[Reissue] = []
    for identifier, address in sorted(where_now.items()):
        before_holder = was.get(address)
        if before_holder is not None and before_holder != identifier:
            reissued.append(
                Reissue(
                    address=address,
                    now_held_by=identifier,
                    was_held_by=before_holder,
                    previous_holder_still_here=before_holder in where_now,
                )
            )
            continue
        previously = where_was.get(identifier)
        if previously is None or previously == address:
            continue
        renamed.append(
            AddressChange(
                stable_id=identifier,
                was=previously,
                now=address,
                old_address_retained=previously in still_held.get(address, frozenset()),
            )
        )

    listed = {one.work_address.casefold() for one in roster.people}
    return AddressReading(
        source=roster.source,
        renamed=tuple(renamed),
        reissued=tuple(reissued),
        arrived=tuple(sorted(set(where_now) - set(where_was))),
        # Absence is not deletion. `may_remove` is the roster's own answer and is asked
        # rather than reimplemented, so the two cannot disagree about what completeness means.
        departed=tuple(sorted(set(where_was) - set(where_now))) if roster.may_remove() else (),
        identified=tuple(sorted(listed & set(now))),
        unidentified=tuple(sorted(listed - set(now))),
    )
