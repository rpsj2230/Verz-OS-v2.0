"""What a changed work address means, held to the rule that it usually means nothing safe.

The address is the join between a roster entry and the person who signs in, and it is also
the field that changes when somebody marries or the company rebrands its domain. Every test
here is about a consequence of one decision: **a changed address is a different person unless
the source carried an identifier that says otherwise**, because the alternative is an account
takeover with no exploit in it. On a source where a name or a similar address is enough,
anybody who can edit the roster inherits whoever they choose to resemble.

Driven from the recorded payloads through the adapters rather than from identifier maps
written here, wherever the fact under test is one an adapter produces. A map built in a test
is a map that agrees with the test, and the question of which field a directory's identity
lives in is exactly the one an invented map answers for free.

Task ids: M1.6.8
"""

from __future__ import annotations

import inspect
from dataclasses import fields

import pytest

from brain.identity import staff_address
from brain.identity.staff_adapters import GoogleWorkspaceSource, SpreadsheetSource
from brain.identity.staff_address import (
    AddressChange,
    AddressError,
    AddressReading,
    Reissue,
    address_changes,
)
from brain.identity.staff_source import Roster, StaffRecord
from tests.fixtures import roster_payloads as recorded


def workspace(*pages: dict[str, object]) -> GoogleWorkspaceSource:
    return GoogleWorkspaceSource(pages=list(pages))


def last_month() -> GoogleWorkspaceSource:
    return workspace(
        recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE, recorded.GOOGLE_WORKSPACE_USERS_PAGE_TWO
    )


def roster_of(*addresses: str, complete: bool = True) -> Roster:
    return Roster(
        source="google_workspace",
        people=tuple(
            StaffRecord(work_address=one, display_name=f"Person {at}")
            for at, one in enumerate(addresses)
        ),
        complete=complete,
    )


def between(before: GoogleWorkspaceSource, after: GoogleWorkspaceSource) -> AddressReading:
    """One reading against the next, both parsed from recorded payloads."""
    was, now = before.reading(), after.reading()
    return address_changes(
        roster=now.roster,
        previous=was.stable_ids,
        current=now.stable_ids,
        retained=now.aliases,
    )


# --- the decision -----------------------------------------------------------------------


def test_a_changed_address_with_an_identifier_behind_it_is_one_person_who_moved() -> None:
    """**The case the whole module exists for, read end to end from the payloads.** Ada
    married, her primary address changed, and the two things that make this a move rather than
    a departure and an arrival are both in the body and neither is her name: the Workspace
    `id` is unchanged and the old address is now an alias.

    Asserted as one `AddressChange` rather than as a count, because the fields are what a
    caller acts on: rebinding the wrong direction unbinds the person who is here.

    The siblings matter as much. Nobody arrived, nobody departed, and the other two people did
    not move, so this is a rename and not a rename plus churn.

    Delete this and a marriage is a resignation, on every source in the system."""
    found = between(last_month(), workspace(recorded.GOOGLE_WORKSPACE_AFTER_A_RENAME))

    assert found.renamed == (
        AddressChange(
            stable_id="100000000000000000001",
            was="ada@example.com",
            now="ada.byron@example.com",
            old_address_retained=True,
        ),
    )
    assert found.arrived == ()
    assert found.departed == ()
    assert found.reissued == ()


def test_a_changed_address_with_nothing_behind_it_is_not_recognisable_as_a_move() -> None:
    """A hand-kept sheet issues no identifier, so a changed address on one is an arrival and,
    on an incomplete sheet, only an arrival. The person keeps two entries until somebody says
    otherwise, which is untidy and visible, and the alternative is moving a live sign-in join
    onto an address on the strength of a resemblance.

    `renames_are_recognisable` is the answer a caller needs: it is a fact about the source
    rather than about this run, so there is no configuration that changes it.

    Delete this and a spreadsheet grows the ability to say two addresses are one person, which
    is the ability to say whose principal you inherit."""
    sheet = SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT).reading()

    found = address_changes(
        roster=sheet.roster, previous={}, current=sheet.stable_ids, retained=sheet.aliases
    )

    assert sheet.stable_ids == {}
    assert found.renamed == ()
    assert not found.renames_are_recognisable
    assert set(found.unidentified) == {one.work_address for one in sheet.roster.people}


def test_a_directory_that_changed_nothing_can_still_recognise_a_move() -> None:
    """The sibling that keeps `renames_are_recognisable` honest. A directory on a quiet week
    changes nothing at all, and an answer read off whether anything moved would report that
    the source cannot recognise a rename when what happened is that nobody had one.

    Delete this and the flag becomes "did anything change", which is a different question and
    is already answered by the lists themselves."""
    found = between(last_month(), last_month())

    assert found.renamed == ()
    assert found.arrived == ()
    assert found.renames_are_recognisable
    assert found.identified == (
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    )


def test_every_address_in_the_roster_is_either_identified_or_not_and_never_both() -> None:
    """The two lists partition the roster, which is what lets a caller act on them: an address
    in neither is a person no rule here has an opinion about, and one in both is a
    contradiction a reader would have to resolve.

    Delete this and a person can fall out of both lists, and a change to their address is
    handled by nothing at all."""
    reading = last_month().reading()
    mixed = address_changes(
        roster=reading.roster,
        previous={},
        current={"ada@example.com": "100000000000000000001"},
    )

    assert set(mixed.identified) & set(mixed.unidentified) == set()
    assert set(mixed.identified) | set(mixed.unidentified) == {
        one.work_address for one in reading.roster.people
    }


def test_no_function_here_can_be_handed_a_display_name() -> None:
    """**The rule made structural rather than remembered.** Matching a changed address to a
    person by their name is an account takeover with no exploit in it, and it is wrong in the
    ordinary case too: a name is exactly what changes when somebody marries, and the address
    is what stays.

    Asserted over the parameters of every public function and the fields of every value this
    module returns, rather than over one signature, because the way a name arrives is as a
    convenience on the type rather than as an argument to the function. A future author who
    wants to match on one has to change a signature first, which is a diff with a reviewer on
    it.

    Matched on whole words rather than on substrings, because `renamed` contains `name` and is
    not one. A substring rule here would fail on the module as it stands, and the version of
    this test that passes by loosening the rule is worse than no test.

    Delete this and the field arrives as a helpful addition to `AddressChange`, and the rule
    survives only in prose."""
    named = {"name", "names", "fullname", "display", "given", "surname", "family"}

    def words(text: str) -> set[str]:
        return set(text.casefold().split("_"))

    checked = 0
    for label, value in vars(staff_address).items():
        if label.startswith("_") or not inspect.isfunction(value):
            continue
        checked += 1
        for parameter in inspect.signature(value).parameters:
            assert not words(parameter) & named, f"{label} takes {parameter}"

    for kind in (AddressChange, Reissue, AddressReading):
        checked += 1
        for one in fields(kind):
            assert not words(one.name) & named, f"{kind.__name__} carries {one.name}"

    assert checked >= 4, f"only {checked} things were examined, so this checked almost nothing"


def test_completeness_is_read_off_the_roster_and_is_not_something_a_caller_may_state() -> None:
    """The one thing in this answer that removes something is whether a missing identifier is
    a departure, and a caller able to pass that in is a caller able to promise on the source's
    behalf. The adapters derive it from the payload for the same reason.

    Asserted on the signature, because the check that matters is that the parameter does not
    exist rather than that nobody currently passes it.

    Delete this and a caller in a hurry passes True, and the completeness rule is a suggestion
    everywhere it is inconvenient."""
    taken = set(inspect.signature(address_changes).parameters)

    assert taken == {"roster", "previous", "current", "retained"}


# --- the new address already belonging to somebody else ------------------------------------


def test_an_address_that_has_changed_hands_is_a_reissue_and_never_a_rename() -> None:
    """**The case that must not be automated.** Grace left, the company handed her address to
    a new joiner, and the joiner's identifier now sits at an address whose previous holder is
    still bound to a principal here. The identifier is right that this is a different person;
    that is precisely the reason not to complete the join, because the grants attached to the
    address did not change hands with it.

    Reissuing an address is ordinary practice and the point of it is that mail keeps working,
    which is what makes it arrive looking harmless.

    Delete this and a new joiner inherits a leaver's principal on the first sync after their
    account is created."""
    found = between(last_month(), workspace(recorded.GOOGLE_WORKSPACE_AFTER_A_REISSUE))

    assert found.reissued == (
        Reissue(
            address="grace@example.com",
            now_held_by="100000000000000000077",
            was_held_by="100000000000000000002",
            previous_holder_still_here=False,
        ),
    )
    assert found.renamed == ()
    assert found.needs_a_person == found.reissued


def test_a_new_joiner_at_a_reissued_address_is_an_arrival_and_a_reissue_at_once() -> None:
    """Both facts are true and both have to be said. They are provisioned, which belongs to
    `brain.identity.lifecycle.provision`; and the address they were given is one this system
    already knows, which belongs to a person.

    Delete this and one of the two is dropped: either the joiner never gets an account, or
    they get one bound to somebody else's address with nothing flagged."""
    found = between(last_month(), workspace(recorded.GOOGLE_WORKSPACE_AFTER_A_REISSUE))

    assert "100000000000000000077" in found.arrived
    assert [one.now_held_by for one in found.reissued] == ["100000000000000000077"]


def test_two_people_exchanging_addresses_is_reported_as_two_addresses_changing_hands() -> None:
    """A swap happens when a mistake made at onboarding is corrected, and it is the shape that
    makes applying one half at a time dangerous: binding either person to their new address
    binds them to the other's until the second half lands.

    `previous_holder_still_here` is what distinguishes it from an ordinary reissue, and it is
    reported rather than raised because the swap is a legitimate thing for a directory to do.

    Delete this and a correction made in the directory is applied one row at a time, and for
    as long as that takes each person holds the other's join."""
    found = address_changes(
        roster=roster_of("first@example.com", "second@example.com"),
        previous={"first@example.com": "id-one", "second@example.com": "id-two"},
        current={"second@example.com": "id-one", "first@example.com": "id-two"},
    )

    assert found.renamed == ()
    assert sorted(one.address for one in found.reissued) == [
        "first@example.com",
        "second@example.com",
    ]
    assert all(one.previous_holder_still_here for one in found.reissued), found.reissued


def test_a_reissued_address_is_never_in_the_moves_a_caller_may_apply() -> None:
    """The invariant that makes `renamed` safe to act on without re-checking it. A caller
    executes `renamed` and reads `reissued`, and an address in both would be applied by the
    first while the second said not to.

    Stated over all three cases at once rather than assumed from the two above, because it is
    a property of the answer rather than of any one input.

    Delete this and the two lists can overlap, and which one a caller consults decides whether
    somebody inherits another person's grants."""
    for after in (
        recorded.GOOGLE_WORKSPACE_AFTER_A_RENAME,
        recorded.GOOGLE_WORKSPACE_AFTER_A_REISSUE,
    ):
        found = between(last_month(), workspace(after))
        moved = {one.now for one in found.renamed}
        changed_hands = {one.address for one in found.reissued}
        assert moved & changed_hands == set(), (moved, changed_hands)


# --- absence, still, is not deletion --------------------------------------------------------


def test_a_missing_identifier_is_a_departure_only_when_the_roster_promised_completeness() -> None:
    """A rename is not deletion and neither is an absence, and the completeness rule applies to
    identity exactly as it applies to membership: a source that did not promise the whole list
    has not said that the identifier it failed to mention has gone.

    Both directions, because a rule that never reported a departure would make a directory
    unable to retire anybody and would pass the first half of this alone. `may_remove` is the
    roster's own answer and is asked rather than reimplemented.

    Delete this and the day a directory pages badly, every identifier it missed is a leaver."""
    partial = address_changes(
        roster=roster_of("here@example.com", complete=False),
        previous={"here@example.com": "id-one", "gone@example.com": "id-two"},
        current={"here@example.com": "id-one"},
    )
    whole = address_changes(
        roster=roster_of("here@example.com", complete=True),
        previous={"here@example.com": "id-one", "gone@example.com": "id-two"},
        current={"here@example.com": "id-one"},
    )

    assert partial.departed == ()
    assert whole.departed == ("id-two",)


# --- readings that cannot be compared at all -------------------------------------------------


def test_one_identifier_at_two_addresses_at_once_stops_the_comparison() -> None:
    """A reading saying one person is at two addresses cannot answer which of them they moved
    to, and every comparison after that point inherits the ambiguity. `Roster` refuses the
    mirror image at construction, where one address names two people, for the same reason.

    Refused rather than resolved, because there is no answer to choose between.

    Delete this and whichever address the dictionary happened to iterate first decides where
    somebody's sign-in join is pointed."""
    with pytest.raises(AddressError, match="more than one address"):
        address_changes(
            roster=roster_of("one@example.com"),
            previous={},
            current={"one@example.com": "id-one", "two@example.com": "id-one"},
        )


def test_two_spellings_of_one_address_naming_two_people_stops_the_comparison() -> None:
    """Folding is right, because a directory that exports one address in two capitalisations
    is a directory rather than a hypothetical. Folding quietly is not: a dict comprehension
    over a collision keeps whichever came last, and which of two people an address belongs to
    is not a question to answer by iteration order.

    The sibling proves folding still happens: two spellings naming the same person are one
    person and not an error.

    Delete this and a collision decides somebody's identity silently, in whichever direction
    the source happened to serialise its rows."""
    with pytest.raises(AddressError, match="two ways"):
        address_changes(
            roster=roster_of("one@example.com"),
            previous={"One@example.com": "id-one", "one@example.com": "id-two"},
            current={"one@example.com": "id-two"},
        )

    agreeing = address_changes(
        roster=roster_of("one@example.com"),
        previous={"One@example.com": "id-one", "one@example.com": "id-one"},
        current={"one@example.com": "id-one"},
    )
    assert agreeing.renamed == ()
    assert agreeing.departed == ()


# --- what the old address does next ----------------------------------------------------------


def test_an_old_address_the_source_still_holds_is_marked_as_one_it_cannot_hand_on() -> None:
    """Workspace keeps the old address as an alias after a rename, which is why mail keeps
    arriving, and it is also the guarantee that the address cannot be given to somebody else
    tomorrow. False does not mean the rename is doubtful: Lark and an LDAP directory publish
    no such list, and requiring one would make every rename on those sources unrecognisable.
    What False means is that the old address is free, and that is what makes rebinding
    promptly a safety measure rather than tidiness.

    Both cases, from the same pair of readings, so the flag is shown to be read from the
    payload rather than defaulted.

    Delete this and an operator cannot tell a rename whose old address is parked from one
    whose old address is about to be somebody else's."""
    retained = between(last_month(), workspace(recorded.GOOGLE_WORKSPACE_AFTER_A_RENAME))
    without_the_alias_list = address_changes(
        roster=roster_of("ada.byron@example.com"),
        previous={"ada@example.com": "100000000000000000001"},
        current={"ada.byron@example.com": "100000000000000000001"},
    )

    assert [one.old_address_retained for one in retained.renamed] == [True]
    assert [one.old_address_retained for one in without_the_alias_list.renamed] == [False]
    assert without_the_alias_list.renamed[0].was == "ada@example.com"
