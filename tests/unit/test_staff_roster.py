"""What one scheduled read of the staff list writes, decided without a database.

`brain.identity.staff_roster.application_for` is the pure half of the scheduled sync: the roster
the source answered with, the members the last applied run left behind and when that run was, in;
the rows to write and the run record's lists, out. Every test here builds the roster the adapters
would build and the members the store would read, and asks what gets written.

Task ids: M1.6.1, M1.6.2, M1.6.3, M1.6.7, M1.6.8, M1.6.12
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.identity.staff_roster import (
    AN_ADDRESS_CHANGED_HANDS,
    APPLIED_OUTCOMES,
    Application,
    LeftBecause,
    MemberWrite,
    RunOutcome,
    StoredMember,
    Write,
    application_for,
    digest_of,
)
from brain.identity.staff_source import Asserts, Roster, StaffRecord, trust_for
from brain.tables.staff import LEFT_BECAUSE, RUN_OUTCOMES

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
LAST_RUN = datetime(2999, 1, 1, 2, 0, tzinfo=UTC)
LEFT_BEFORE = datetime(2998, 6, 1, 2, 0, tzinfo=UTC)

ADA = StaffRecord("ada@example.com", "Ada", department="finance")
BEN = StaffRecord("ben@example.com", "Ben", department="design")
CAL = StaffRecord("cal@example.com", "Cal", department="design")


def roster(*people: StaffRecord, source: str = "lark", complete: bool = True) -> Roster:
    return Roster(source=source, people=people, complete=complete, asserts=trust_for(source))


def member(
    person: StaffRecord, *, stable_id: str | None = None, left: bool = False
) -> StoredMember:
    return StoredMember(
        address_hash=digest_of(person.work_address),
        display_name=person.display_name,
        stable_id=stable_id,
        left_at=LEFT_BEFORE if left else None,
    )


def apply(
    listed: Roster,
    members: tuple[StoredMember, ...] = (),
    *,
    last_applied: datetime | None = LAST_RUN,
    stable_ids: dict[str, str] | None = None,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> Application:
    return application_for(
        listed,
        stable_ids=stable_ids or {},
        aliases=aliases or {},
        members=members,
        last_applied=last_applied,
    )


def writes_of(found: Application, kind: Write) -> list[MemberWrite]:
    return [one for one in found.writes if one.write is kind]


def test_the_first_run_of_a_source_adds_everybody_it_lists_and_marks_nobody_as_left() -> None:
    """M1.6.12 and the first-run rule, through the run rather than the dry run alone.

    Delete this and a first run's plan could be applied with removals in it, which on a source
    pointed at the wrong organisational unit marks everybody outside it as having left."""
    found = apply(roster(ADA, BEN), (member(CAL),), last_applied=None)

    assert [one.display_name for one in writes_of(found, Write.ADD)] == ["Ada", "Ben"]
    assert writes_of(found, Write.MARK_LEFT) == []
    assert found.added == ("Ada", "Ben")
    assert found.marked_left == ()
    assert any("never been applied" in why for why in found.withheld)
    assert found.outcome is RunOutcome.APPLIED


def test_a_complete_roster_on_a_later_run_marks_the_person_it_stopped_naming() -> None:
    """The positive case of the rule above: the second run is the one that can remove.

    Delete this and a sync that never marks anybody as having left satisfies every refusal here,
    and a leaver's agents are never listed for a new owner (M1.8.9)."""
    found = apply(roster(ADA, BEN), (member(ADA), member(BEN), member(CAL)))

    (gone,) = writes_of(found, Write.MARK_LEFT)
    assert gone.address_hash == digest_of("cal@example.com")
    assert gone.left_because is LeftBecause.ABSENT_FROM_COMPLETE_ROSTER
    assert found.marked_left == ("Cal",)
    assert found.added == ()


def test_an_incomplete_roster_adds_and_never_marks_anybody_as_left() -> None:
    """M1.6.7: an incomplete run may add and may never remove, applied rather than only planned.

    Delete this and a paged read that stopped early is written as a company that halved."""
    found = apply(
        roster(ADA, StaffRecord("dee@example.com", "Dee"), complete=False),
        (member(ADA), member(BEN), member(CAL)),
    )

    assert [one.display_name for one in writes_of(found, Write.ADD)] == ["Dee"]
    assert writes_of(found, Write.MARK_LEFT) == []
    assert any("complete list" in why for why in found.withheld)


def test_a_person_the_source_says_has_left_is_marked_even_on_an_incomplete_run() -> None:
    """The one removal that survives incompleteness, because the source stated a fact.

    Delete this and a directory that keeps leavers as disabled accounts never produces a leaver."""
    gone = StaffRecord("ben@example.com", "Ben", active=False)
    found = apply(roster(ADA, gone, complete=False), (member(ADA), member(BEN)))

    (marked,) = writes_of(found, Write.MARK_LEFT)
    assert marked.left_because is LeftBecause.SOURCE_SAYS_LEFT
    assert marked.display_name == "Ben"
    assert writes_of(found, Write.REFRESH) == [
        MemberWrite(Write.REFRESH, digest_of("ada@example.com"), "Ada", department="finance")
    ]


def test_somebody_already_marked_as_having_left_is_not_marked_twice_and_rejoins_when_listed() -> (
    None
):
    """A leaver is excluded from `known`, so being listed again is an addition that clears the mark.

    Delete this and a person who came back stays marked as having left for ever, or a leaver is
    re-marked every night with a new time that says they left today."""
    back = apply(roster(ADA, BEN), (member(ADA), member(BEN, left=True)))
    still_gone = apply(roster(ADA), (member(ADA), member(BEN, left=True)))

    assert [one.display_name for one in writes_of(back, Write.ADD)] == ["Ben"]
    assert writes_of(still_gone, Write.MARK_LEFT) == []


def test_a_department_is_kept_only_for_a_source_trusted_to_assert_one() -> None:
    """M1.6.3 and M1.6.4 on the applied path: a spreadsheet lists people and places nobody.

    Delete this and a sheet anybody can edit decides which department bounds somebody's grants."""
    sheet = apply(roster(ADA, source="spreadsheet", complete=False), last_applied=None)
    directory = apply(roster(ADA, source="lark"), last_applied=None)

    assert Asserts.DEPARTMENT not in trust_for("spreadsheet")
    assert writes_of(sheet, Write.ADD)[0].department is None
    assert writes_of(directory, Write.ADD)[0].department == "finance"


def test_the_roster_keeps_a_digest_of_each_address_and_never_the_address() -> None:
    """The member rows carry the email binding's own digest, so no write holds an address.

    Delete this and the roster becomes the company phone book `brain.tables.identity` refuses."""
    found = apply(roster(ADA, BEN), (member(CAL),), last_applied=LAST_RUN)

    for one in found.writes:
        assert "@" not in one.address_hash
        assert len(one.address_hash) == 64
    assert digest_of("Ada@Example.com") == digest_of("ada@example.com")


def test_an_address_that_moved_under_a_stable_identifier_is_a_rename_and_not_a_leaver() -> None:
    """M1.6.8 wired: `address_changes` turns a leaver and a joiner into one moved row.

    Delete this and somebody who married is marked as having left, their agents are listed for a
    new owner, and a stranger with their name joins."""
    renamed = StaffRecord("ada.b@example.com", "Ada")
    found = apply(
        roster(renamed, BEN),
        (member(ADA, stable_id="u-ada"), member(BEN, stable_id="u-ben")),
        stable_ids={"ada.b@example.com": "u-ada", "ben@example.com": "u-ben"},
    )

    (moved,) = writes_of(found, Write.RENAME)
    assert moved.was_hash == digest_of("ada@example.com")
    assert moved.address_hash == digest_of("ada.b@example.com")
    assert writes_of(found, Write.MARK_LEFT) == []
    assert writes_of(found, Write.ADD) == []
    assert found.renamed == ("Ada",)


def test_an_address_that_changed_hands_is_written_for_nobody_and_said_to_need_a_person() -> None:
    """A reissue is never automated: the row is not refreshed onto its new holder.

    Delete this and a joiner handed a leaver's address inherits the leaver's roster entry."""
    found = apply(
        roster(ADA, BEN),
        (member(ADA, stable_id="u-ada"), member(BEN, stable_id="u-ben")),
        stable_ids={"ada@example.com": "u-new", "ben@example.com": "u-ben"},
    )

    assert AN_ADDRESS_CHANGED_HANDS in found.withheld
    refreshed = {one.address_hash for one in writes_of(found, Write.REFRESH)}
    assert digest_of("ada@example.com") not in refreshed
    assert digest_of("ben@example.com") in refreshed


def test_a_run_that_changes_nobody_is_unchanged_and_one_that_does_is_applied() -> None:
    """A refresh changes nobody, so it does not make a run applied.

    Delete this and every night reads as a night somebody joined."""
    quiet = apply(roster(ADA), (member(ADA),))
    busy = apply(roster(ADA, BEN), (member(ADA),))

    assert quiet.outcome is RunOutcome.UNCHANGED
    assert busy.outcome is RunOutcome.APPLIED
    assert {RunOutcome.APPLIED, RunOutcome.UNCHANGED} == APPLIED_OUTCOMES


def test_the_tables_closed_words_are_the_enums_own() -> None:
    """The check constraints and the enums agree, read from two modules.

    Delete this and a new outcome passes every test here and is refused by the database."""
    assert sorted(one.value for one in RunOutcome) == sorted(RUN_OUTCOMES)
    assert sorted(one.value for one in LeftBecause) == sorted(LEFT_BECAUSE)
