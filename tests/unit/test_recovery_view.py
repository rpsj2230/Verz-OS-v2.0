"""The recovery panel held to one rule: fresh copies nobody has read back must look alarming.

Two properties are pinned here, and each fails quietly in the reassuring direction.

**A backup timestamp beside a last verified restore that is old or absent reads as alarming,
never as blank space.** A renderer handed `None` draws a dash, and a dash under that heading
beside a copy taken half an hour ago is the field somebody checks before deciding not to
worry. So the tests that build an unproven install ask the same three questions: is the
verdict outside `SETTLED`, is the field a `Fact` carrying a sentence rather than an empty slot,
and are the copy times still shown beside it. The positive case sits beside the refusals,
because a panel that refuses every reassurance passes every refusal.

**DENIED and ABSENT are indistinguishable on this screen because nothing on it is narrowed.**
The rows are the install's own copies, always one per coverage, and the panel takes no reader,
so there is no set of hidden items for a count to describe and no shorter list for a
subtraction to be read off. The tests hold the shape rather than the prose: the rows are the
same on a healthy install and on one with nothing copied, the fields of `Panel` are pinned,
and `panel` has no parameter a reader could arrive through.

The instants are in 2999 for the reason `CLAUDE.md` records: nothing here is about the present,
and a fixture near the wall clock is a test that reports a defect on a morning nobody chose.

Task ids: M27.6.2
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Sequence
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.console.installation import Source
from brain.console.recovery_view import (
    ANSWERS,
    LAST_VERIFIED_FACT,
    NEWEST_FACT,
    SCHEDULE_FACT,
    SETTLED,
    Assurance,
    CopyState,
    Panel,
    RecoveryViewError,
    assurance_of,
    copy_states,
    panel,
)
from brain.console.screens import screen
from brain.console.version_view import Answer
from brain.console.workspace import intersections_in
from brain.launch import LaunchError, service_level
from brain.ops.backup_manifest import DRILL_SUFFIX, Unreadable, read_drills
from brain.ops.recovery import (
    DRILL_INTERVAL_DAYS,
    SCHEDULE,
    Backup,
    Check,
    CheckRun,
    Coverage,
    Drill,
    Method,
    RecoveryError,
    Scheduled,
    Verification,
    verification_of,
)
from brain.ops.reliability import recovery_objective

#: Far outside any wall clock. Every clock on this panel is a parameter.
NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)

#: The tightest profile: an hour is the recovery point and two hours the recovery time.
PROFILE = "full"
OBJECTIVE = recovery_objective(PROFILE)

SOURCE = Path("src/brain/console/recovery_view.py")


def a_copy(coverage: Coverage, *, seconds_ago: int = 1_800) -> Backup:
    """A copy of `coverage` that restores to `seconds_ago` before `NOW`."""
    at = NOW - timedelta(seconds=seconds_ago)
    return Backup(
        backup_id=f"{coverage.value}-{seconds_ago}",
        coverage=coverage,
        method=Method.FULL,
        destination="off-host",
        started_at=at - timedelta(minutes=5),
        finished_at=at,
        recoverable_to=at,
        size_bytes=4_096,
    )


def fresh() -> list[Backup]:
    """A copy of every coverage from half an hour ago, inside every profile's recovery point."""
    return [a_copy(one) for one in Coverage]


def without(coverage: Coverage) -> list[Backup]:
    """Fresh copies of everything except `coverage`, which nothing has ever copied."""
    return [a_copy(one) for one in Coverage if one is not coverage]


def late(coverage: Coverage, *, by_seconds: int = 1) -> list[Backup]:
    """Fresh copies, except that `coverage` is `by_seconds` past the profile's recovery point."""
    return [
        a_copy(one, seconds_ago=OBJECTIVE.rpo_seconds + by_seconds)
        if one is coverage
        else a_copy(one)
        for one in Coverage
    ]


def rehearsed(*, hours_ago: float = 24, passed: bool = True, seconds: int = 1_800) -> Verification:
    """One rehearsal outcome, built from a drill so that `verification_of` decides it.

    A failure is a permission canary that let a restricted field through, which is the check
    whose failure means the restored copy answers everybody.
    """
    started = NOW - timedelta(hours=hours_ago)
    return verification_of(
        Drill(
            backup_id=f"database-{hours_ago}",
            started_at=started,
            finished_at=started + timedelta(seconds=seconds),
            into_scratch=True,
            checks=tuple(
                CheckRun(
                    check=one,
                    passed=passed or one is not Check.PERMISSION_CANARY,
                    detail=f"asked {one.value} of the restored copy",
                )
                for one in Check
            ),
        )
    )


def built(
    backups: Sequence[Backup] | None = None,
    verifications: Sequence[Verification] = (),
    **changes: Any,
) -> Panel:
    """The panel for an install at `NOW`, with fresh copies unless the test says otherwise."""
    return panel(
        backups=fresh() if backups is None else backups,
        verifications=verifications,
        profile=PROFILE,
        now=NOW,
        **changes,
    )


def one_panel_per_answer() -> dict[Assurance, Panel]:
    """An install in every state this panel can answer, each built through `panel`."""
    ok = rehearsed()
    return {
        Assurance.RECORDS_UNREADABLE: built(
            verifications=[ok],
            unreadable=[Unreadable(where="tuesday" + DRILL_SUFFIX, why="not JSON")],
        ),
        Assurance.NOTHING_COPIED: built(without(Coverage.DATABASE), [ok]),
        Assurance.VERIFICATION_FAILED: built(verifications=[rehearsed(passed=False)]),
        Assurance.NEVER_VERIFIED: built(),
        Assurance.BACKUP_AGED: built(late(Coverage.DATABASE), [ok]),
        Assurance.DRILL_OVERDUE: built(
            verifications=[rehearsed(hours_ago=(DRILL_INTERVAL_DAYS + 1) * 24)]
        ),
        Assurance.SLOWER_THAN_PROMISED: built(
            verifications=[rehearsed(seconds=OBJECTIVE.rto_seconds + 1)]
        ),
        Assurance.RECOVERABLE: built(verifications=[ok]),
    }


# --- the worst state, looking its best -----------------------------------------------------
def test_fresh_copies_nobody_has_read_back_are_never_verified_in_words_beside_their_times():
    """**This is the install this product ships as, and the state the screen exists for.**
    Every coverage copied half an hour ago and no rehearsal has ever restored one. The verdict
    is outside `SETTLED`, the field under last verified restore is an unknown `Fact` carrying a
    sentence rather than an empty slot a renderer fills with a dash, and the copy times are
    still on the screen beside it, measured, because hiding them would throw away the one
    measurement that exists.

    Delete this and the panel can render three recent timestamps over a blank, which reads as
    a screen with nothing to report."""
    shown = built()

    assert shown.assurance is Assurance.NEVER_VERIFIED
    assert shown.assurance not in SETTLED
    assert shown.answer is ANSWERS[Assurance.NEVER_VERIFIED]
    assert shown.drill_is_due is True
    assert shown.measured_rto_seconds is None

    field = shown.last_verified_fact
    assert field.name == LAST_VERIFIED_FACT
    assert field.source is Source.UNKNOWN
    assert field.value == ""
    assert field.because.strip()

    newest = [row.facts[1] for row in shown.copies]
    assert [fact.source for fact in newest] == [Source.MEASURED] * len(Coverage)
    assert [fact.value for fact in newest] == [(NOW - timedelta(seconds=1_800)).isoformat()] * len(
        Coverage
    )


def test_copies_inside_the_promise_with_a_recent_quick_verified_restore_are_recoverable():
    """**The positive case for every refusal in this file.** Without it, a panel answering
    never verified for everything passes all of them, and the screen becomes a permanent alarm
    that teaches people to stop reading it.

    Delete this and the reassuring answer can become unreachable with the suite green."""
    restore = rehearsed()
    shown = built(verifications=[restore])

    assert shown.assurance is Assurance.RECOVERABLE
    assert shown.assurance in SETTLED
    assert shown.drill_is_due is False
    assert shown.last_verified is restore
    assert shown.latest_attempt is restore
    assert shown.measured_rto_seconds == 1_800

    field = shown.last_verified_fact
    assert field.source is Source.MEASURED
    assert field.value == restore.attempted_at.isoformat()


def test_a_verified_restore_older_than_the_interval_beside_fresh_copies_is_overdue():
    """A date under last verified restore that is weeks old looks like an answer, and beside a
    copy from half an hour ago it looks like a current one. It proves the copies of that week
    could be read. The interval itself is due, and an hour inside it is not.

    Delete this and a restore verified once, at installation, keeps the panel reassuring for
    ever."""
    stale = built(verifications=[rehearsed(hours_ago=(DRILL_INTERVAL_DAYS + 30) * 24)])
    edge = built(verifications=[rehearsed(hours_ago=DRILL_INTERVAL_DAYS * 24)])
    inside = built(verifications=[rehearsed(hours_ago=DRILL_INTERVAL_DAYS * 24 - 1)])

    assert stale.assurance is Assurance.DRILL_OVERDUE
    assert stale.drill_is_due is True
    assert stale.last_verified_fact.source is Source.MEASURED
    assert edge.assurance is Assurance.DRILL_OVERDUE
    assert edge.drill_is_due is True
    assert inside.assurance is Assurance.RECOVERABLE
    assert inside.drill_is_due is False


def test_a_failed_rehearsal_after_a_success_leaves_the_date_and_takes_away_the_tick():
    """**The field and the verdict are two questions.** Monday's restore verified and Tuesday's
    permission canary let a restricted field through. The field still says Monday, which is
    true, and its sentence says a later rehearsal failed; the verdict is verification failed.
    A panel built on the field alone renders a recent date and a tick on the evening the
    restored copy answered everybody.

    The sibling is the same install without Tuesday, whose field carries the other sentence.

    Delete this and the newest evidence can be outvoted by an older success."""
    monday = rehearsed(hours_ago=48)
    tuesday = rehearsed(hours_ago=24, passed=False)

    failed = built(verifications=[monday, tuesday])
    passed = built(verifications=[monday])

    assert failed.assurance is Assurance.VERIFICATION_FAILED
    assert failed.last_verified is monday
    assert failed.latest_attempt is tuesday
    assert failed.last_verified_fact.source is Source.MEASURED
    assert failed.last_verified_fact.value == monday.attempted_at.isoformat()

    assert passed.assurance is Assurance.RECOVERABLE
    assert passed.last_verified_fact.value == failed.last_verified_fact.value
    assert passed.last_verified_fact.because != failed.last_verified_fact.because


def test_no_state_hands_a_renderer_a_blank_under_last_verified_restore():
    """Every answer this panel can give, and in every one of them the field is a labelled
    statement: a date when a restore verified, and a sentence saying why not when none has.
    Both sentences a client reads are present in every state too.

    Delete this and one state nobody thought about, reached on a real install, draws the dash."""
    for answer, shown in one_panel_per_answer().items():
        field = shown.last_verified_fact
        assert field.name == LAST_VERIFIED_FACT, answer
        assert field.because.strip(), answer
        assert (field.source is Source.UNKNOWN) == (shown.last_verified is None), answer
        assert (field.value == "") == (field.source is Source.UNKNOWN), answer
        assert shown.answer.says.strip(), answer
        assert shown.answer.what_to_do.strip(), answer


def test_every_answer_has_a_producer_and_the_reassuring_one_has_every_condition_behind_it():
    """`SETTLED` is asserted as a property of the panels `panel` builds rather than as a list
    written here: an answer belongs in it only when a restore verified, the newest rehearsal
    is that restore, no rehearsal is owed, nothing in the bucket was unreadable, every copy is
    inside the recovery point, and the restore finished inside the recovery time.

    Delete this and a member added to the enum later can be drawn with a tick beside it,
    because nothing says which of them may be."""
    panels = one_panel_per_answer()

    assert {answer: shown.assurance for answer, shown in panels.items()} == {
        answer: answer for answer in Assurance
    }
    with_everything_behind_it = {
        answer
        for answer, shown in panels.items()
        if shown.last_verified is not None
        and shown.latest_attempt is shown.last_verified
        and not shown.drill_is_due
        and not shown.unreadable
        and all(row.within_objective for row in shown.copies)
        and (shown.measured_rto_seconds or 0) <= OBJECTIVE.rto_seconds
    }
    assert with_everything_behind_it == set(SETTLED)


# --- the screen and the document a client signs --------------------------------------------
def slower_than_the_promise() -> tuple[Scheduled, ...]:
    """The default schedule with the object store copied at twice the recovery point."""
    return tuple(
        replace(one, every_seconds=OBJECTIVE.rpo_seconds * 2)
        if one.coverage is Coverage.OBJECT_STORE
        else one
        for one in SCHEDULE
    )


def test_the_panel_never_reassures_where_the_service_level_statement_refuses():
    """**A console saying recoverable while the document a client signs refuses is two answers
    to one question, and the console is the one somebody reads.** `service_level` refuses a
    schedule that cannot deliver the recovery point (no schedule at all included), copies that
    cannot deliver it, no verified restore, and a restore slower than promised. Every install
    below that it refuses must be answered outside `SETTLED`, and the healthy one inside, or
    the relation is satisfied by a panel that never reassures anybody.

    The implication runs one way on purpose. A rehearsal going stale is a finding here and not
    a refusal there, so a statement can render beside a panel saying a drill is overdue.

    Delete this and the module's claim that the two cannot disagree is a paragraph."""
    ok = rehearsed()
    installs: dict[str, tuple[list[Backup], list[Verification], tuple[Scheduled, ...]]] = {
        "healthy": (fresh(), [ok], SCHEDULE),
        "never verified": (fresh(), [], SCHEDULE),
        "a coverage never copied": (without(Coverage.DATABASE), [ok], SCHEDULE),
        "a copy past the recovery point": (late(Coverage.OBJECT_STORE), [ok], SCHEDULE),
        "a restore slower than promised": (
            fresh(),
            [rehearsed(seconds=OBJECTIVE.rto_seconds + 1)],
            SCHEDULE,
        ),
        "a rehearsal overdue": (
            fresh(),
            [rehearsed(hours_ago=(DRILL_INTERVAL_DAYS + 1) * 24)],
            SCHEDULE,
        ),
        "a schedule slower than the promise": (fresh(), [ok], slower_than_the_promise()),
        "nothing scheduled and nothing copied": ([], [ok], ()),
        "nothing scheduled and fresh copies": (fresh(), [ok], ()),
    }

    disagreements: list[str] = []
    refused: set[str] = set()
    answered: dict[str, Assurance] = {}
    for label, (backups, verifications, schedule) in installs.items():
        shown = panel(
            backups=backups,
            verifications=verifications,
            profile=PROFILE,
            now=NOW,
            schedule=schedule,
        )
        answered[label] = shown.assurance
        try:
            service_level(
                PROFILE, verifications=verifications, backups=backups, now=NOW, schedule=schedule
            )
        except LaunchError:
            refused.add(label)
            if shown.assurance in SETTLED:
                disagreements.append(f"{label}: refused, and the panel says {shown.assurance}")

    assert disagreements == []
    assert refused == set(installs) - {"healthy", "a rehearsal overdue"}
    assert answered["healthy"] in SETTLED
    assert answered["a restore slower than promised"] is Assurance.SLOWER_THAN_PROMISED
    assert answered["a rehearsal overdue"] is Assurance.DRILL_OVERDUE
    # Pinned to the answer each gets, not only kept out of SETTLED: every answer is a sentence a
    # client reads, and "nothing copied" would be false said over three fresh copies.
    assert answered["a schedule slower than the promise"] is Assurance.BACKUP_AGED
    assert answered["nothing scheduled and nothing copied"] is Assurance.NOTHING_COPIED
    assert answered["nothing scheduled and fresh copies"] is Assurance.BACKUP_AGED


# --- nothing hidden, so nothing counted ----------------------------------------------------
def test_every_coverage_has_the_same_two_rows_whatever_has_been_copied():
    """**No absence is reported by subtraction.** A panel that left out the row for a coverage
    nothing has copied would show two rows where a healthy install shows three, and a reader
    counting them learns the absence without being told it. So the rows are the same on a
    healthy install, on one with a single copy, on one with none and on one where nothing is
    scheduled: every coverage, in declaration order, each with its two statements, and an
    absent copy or an absent schedule is a statement saying so.

    Delete this and a later tidy that skips empty rows turns the missing coverage into a
    count."""

    def shape(shown: Panel) -> list[tuple[Coverage, tuple[str, ...]]]:
        return [(row.coverage, tuple(fact.name for fact in row.facts)) for row in shown.copies]

    healthy = built(verifications=[rehearsed()])
    one_copy = built([a_copy(Coverage.DATABASE)])
    nothing = built([])
    unscheduled = built([], schedule=())

    assert shape(healthy) == shape(one_copy) == shape(nothing) == shape(unscheduled)
    assert [coverage for coverage, _ in shape(nothing)] == list(Coverage)
    assert all(len(set(names)) == 2 for _, names in shape(nothing))

    assert all(row.facts[1].source is Source.MEASURED for row in healthy.copies)
    assert all(row.facts[0].source is Source.DECLARED for row in healthy.copies)
    for row in nothing.copies:
        assert row.facts[1].source is Source.UNKNOWN
        assert row.facts[1].because.strip()
    for row in unscheduled.copies:
        assert row.facts[0].source is Source.UNKNOWN
        assert row.facts[0].because.strip()


def test_the_panel_carries_no_count_and_has_no_way_for_a_reader_to_arrive():
    """**DENIED and ABSENT cannot differ on a screen nothing narrows, and this is what keeps it
    un-narrowed.** Who may open the screen is the registry's `read:backup`. Once it is open,
    what it shows is a function of the bucket and the clock and of nothing about the reader:
    `panel` takes no principal and no entitlement set, and the module computes no reach. With
    no reader there is no hidden set for a count to describe, and the fields are pinned so a
    count cannot arrive as a field either.

    The sibling is that the panel is fully determined by what was observed: built twice from
    the same bucket it is the same panel.

    Delete this and a reader parameter added for a filter turns every row the panel then drops
    into a fact about what that reader may not see."""
    assert {one.name for one in fields(Panel)} == {
        "profile",
        "copies",
        "last_verified",
        "latest_attempt",
        "assurance",
        "drill_is_due",
        "unreadable",
    }
    assert {one.name for one in fields(CopyState)} == {
        "coverage",
        "newest",
        "scheduled_every_seconds",
        "measured_exposure_seconds",
        "objective_seconds",
    }
    assert set(inspect.signature(panel).parameters) == {
        "backups",
        "verifications",
        "profile",
        "now",
        "unreadable",
        "schedule",
        "objectives",
    }
    assert intersections_in(SOURCE.read_text(encoding="utf-8")) == ()

    verifications = [rehearsed(hours_ago=48), rehearsed(passed=False)]
    assert built(verifications=verifications) == built(verifications=verifications)


# --- what the bucket reader hands the panel ------------------------------------------------
def a_drill_record(*, hours_ago: float, passed: bool = True) -> str:
    """One drill record as a runner writes it, so the panel is fed through the bucket reader."""
    started = NOW - timedelta(hours=hours_ago)
    return json.dumps(
        {
            "backup_id": f"database-{hours_ago}",
            "started_at": started.isoformat(),
            "finished_at": (started + timedelta(minutes=20)).isoformat(),
            "into_scratch": True,
            "checks": [
                {"check": one.value, "passed": passed, "detail": f"asked {one.value}"}
                for one in Check
            ],
        }
    )


def test_a_truncated_record_beside_an_older_success_refuses_the_tick_and_names_the_file():
    """**The rehearsal that fell over is the one whose record is truncated.** Dropping it would
    leave Monday's success as the newest evidence and the panel recoverable, which is the one
    direction losing a record moves this screen. Read through `read_drills` rather than built
    by hand, so the panel is tested against what the bucket reader actually hands it.

    The sibling is the same bucket without the broken file, which is recoverable.

    Delete this and last night's failure, written halfway, shows as last month's success."""
    monday = ("monday" + DRILL_SUFFIX, a_drill_record(hours_ago=48))
    tuesday = ("tuesday" + DRILL_SUFFIX, '{"backup_id": "database-2999')

    verifications, unreadable = read_drills([monday, tuesday])
    broken = built(verifications=verifications, unreadable=unreadable)
    kept, nothing_unreadable = read_drills([monday])
    clean = built(verifications=kept, unreadable=nothing_unreadable)

    assert broken.assurance is Assurance.RECORDS_UNREADABLE
    assert [one.where for one in broken.unreadable] == ["tuesday" + DRILL_SUFFIX]
    assert broken.last_verified is not None
    assert clean.assurance is Assurance.RECOVERABLE
    assert clean.unreadable == ()


# --- the refusals on the reassuring answer -------------------------------------------------
def reassuring() -> Panel:
    """A panel `panel` built as recoverable, so each refusal below breaks one thing in it."""
    shown = built(verifications=[rehearsed()])
    assert shown.assurance in SETTLED
    return shown


def test_a_panel_cannot_claim_the_reassuring_answer_without_a_verified_restore():
    """The refusal is on the panel as well as in `assurance_of`, because a panel is a value
    anybody can construct and the reassuring one is the value worth forging by accident. This
    is the blank field in its purest form: fresh copies, no restore, and a tick.

    The sibling is `reassuring` itself, which constructs.

    Delete this and a caller assembling a panel by hand can draw recoverable over a field that
    has never been filled."""
    with pytest.raises(RecoveryViewError, match="no restore has ever verified"):
        replace(reassuring(), last_verified=None)


def test_a_panel_cannot_claim_the_reassuring_answer_when_the_newest_rehearsal_did_not_verify():
    """Monday's success in the field and Tuesday's failure as the newest attempt, drawn as
    recoverable. A verified restore beside no attempt at all is refused too, because the two
    fields then disagree about whether any rehearsal happened.

    Delete this and the tick outlives the failure that should have taken it away."""
    shown = reassuring()

    with pytest.raises(RecoveryViewError, match="most recent rehearsal did not verify"):
        replace(shown, latest_attempt=rehearsed(hours_ago=1, passed=False))
    with pytest.raises(RecoveryViewError, match="most recent rehearsal did not verify"):
        replace(shown, latest_attempt=None)


def test_a_panel_cannot_claim_the_reassuring_answer_with_a_rehearsal_owed():
    """Delete this and a verification from the week the install was built keeps a hand-built
    panel reassuring, with only a boolean beside it disagreeing."""
    with pytest.raises(RecoveryViewError, match="overdue"):
        replace(reassuring(), drill_is_due=True)


def test_a_panel_cannot_claim_the_reassuring_answer_with_a_copy_outside_the_recovery_point():
    """Rows the schedule copies are held to the recovery point, and when the schedule copies
    nothing at all every row is, however fresh, because nothing will take the next copy.

    Delete this and a copy an hour and a second behind, on a profile promising an hour, sits
    under a tick on a panel somebody assembled, and so do fresh copies nothing will repeat."""
    behind = copy_states(late(Coverage.CONFIGURATION), profile=PROFILE, now=NOW)
    unrepeated = copy_states(fresh(), profile=PROFILE, now=NOW, schedule=())

    with pytest.raises(RecoveryViewError, match="configuration is outside the recovery point"):
        replace(reassuring(), copies=behind)
    with pytest.raises(RecoveryViewError, match="is outside the recovery point"):
        replace(reassuring(), copies=unrepeated)


def test_a_panel_cannot_claim_the_reassuring_answer_over_a_record_nobody_could_read():
    """The file is named in the refusal, because a reader looking at a bucket has no other way
    to find which object complained.

    Delete this and a hand-built panel can be recoverable about whichever records happened to
    parse."""
    broken = (Unreadable(where="tuesday" + DRILL_SUFFIX, why="not JSON"),)

    with pytest.raises(RecoveryViewError) as caught:
        replace(reassuring(), unreadable=broken)

    assert "tuesday" + DRILL_SUFFIX in str(caught.value)


def test_a_panel_cannot_claim_the_reassuring_answer_about_no_copies_at_all():
    """Delete this and a panel with no rows, which is an install nobody measured, can carry the
    tick."""
    with pytest.raises(RecoveryViewError, match="no copies"):
        replace(reassuring(), copies=())


def test_every_unreassuring_answer_can_be_stated_with_nothing_behind_it():
    """**The refusals are on the reassuring answer alone, and this is the sibling proving it.**
    Stating that a drill is overdue or that nothing was copied too firmly costs a reader
    nothing, so a panel carrying no copies, no restore and no rehearsal constructs for every
    other answer.

    Delete this and a refusal that fires for every answer passes every test above it."""
    for answer in Assurance:
        if answer in SETTLED:
            continue
        stated = Panel(
            profile=PROFILE,
            copies=(),
            last_verified=None,
            latest_attempt=None,
            assurance=answer,
            drill_is_due=True,
        )
        assert stated.answer is ANSWERS[answer]


# --- the order the questions are asked in --------------------------------------------------
def test_the_questions_are_asked_in_the_order_the_module_argues_for():
    """**The order is the argument.** An unreadable record before everything, because it is
    true whatever the rest would say. A coverage never copied before any rehearsal, because a
    rehearsal has nothing to read. A failed rehearsal before an absent one, because it names a
    fault to chase today. Both before an aged copy, an aged copy before a rehearsal going
    stale, and that before a restore being slow.

    Each line holds two findings at once and asserts the earlier question wins, so swapping
    any adjacent pair of questions fails a line.

    Delete this and a reorder that reads as tidying changes what a person with two problems is
    told to fix first."""
    unreadable = [Unreadable(where="tuesday" + DRILL_SUFFIX, why="not JSON")]
    failed = [rehearsed(passed=False)]
    stale = (DRILL_INTERVAL_DAYS + 1) * 24

    assert built([], failed, unreadable=unreadable).assurance is Assurance.RECORDS_UNREADABLE
    assert built(without(Coverage.DATABASE), failed).assurance is Assurance.NOTHING_COPIED
    assert built(verifications=failed).assurance is Assurance.VERIFICATION_FAILED
    assert built(late(Coverage.DATABASE), failed).assurance is Assurance.VERIFICATION_FAILED
    assert built(late(Coverage.DATABASE)).assurance is Assurance.NEVER_VERIFIED
    assert (
        built(late(Coverage.DATABASE), [rehearsed(hours_ago=stale)]).assurance
        is Assurance.BACKUP_AGED
    )
    assert (
        built(
            verifications=[rehearsed(hours_ago=stale, seconds=OBJECTIVE.rto_seconds + 1)]
        ).assurance
        is Assurance.DRILL_OVERDUE
    )


# --- the edges of the two figures ----------------------------------------------------------
def test_a_copy_exactly_at_the_recovery_point_is_inside_it_and_a_second_later_is_not():
    """The promise is no more than an hour, so an hour keeps it and an hour and a second breaks
    it. The wrong comparison in either direction is quiet: one refuses to reassure at the
    moment the promise is exactly kept, the other reassures a second after it broke.

    Delete this and the comparison can move by a second in either direction unobserved."""
    ok = [rehearsed()]
    exactly = built(late(Coverage.DATABASE, by_seconds=0), ok)
    past = built(late(Coverage.DATABASE, by_seconds=1), ok)

    assert exactly.assurance is Assurance.RECOVERABLE
    assert all(row.within_objective for row in exactly.copies)
    assert past.assurance is Assurance.BACKUP_AGED
    assert [row.coverage for row in past.copies if not row.within_objective] == [Coverage.DATABASE]


def test_a_restore_exactly_as_slow_as_promised_keeps_it_and_a_second_slower_does_not():
    """Delete this and a restore that took two hours and a second, on a profile promising two
    hours, is drawn as recoverable while the service level statement refuses it."""
    exactly = built(verifications=[rehearsed(seconds=OBJECTIVE.rto_seconds)])
    slower = built(verifications=[rehearsed(seconds=OBJECTIVE.rto_seconds + 1)])

    assert exactly.assurance is Assurance.RECOVERABLE
    assert slower.assurance is Assurance.SLOWER_THAN_PROMISED
    assert slower.measured_rto_seconds == OBJECTIVE.rto_seconds + 1


def test_a_coverage_nothing_schedules_is_not_a_finding_here_and_is_still_shown_as_absent():
    """**The same coverages count here as in the document a client signs.** `service_level`
    skips a coverage the schedule does not copy and `backup_policy_gaps` reports it, so the
    panel skips it too rather than being the second of two answers about which coverages
    count. What it may not do is hide it or talk over it: the rows still say nothing schedules
    it and nothing copied it, and the reassuring sentence claims only what the schedule copies.

    The sibling is the empty schedule in
    `test_the_panel_never_reassures_where_the_service_level_statement_refuses`, which both
    sides refuse.

    Delete this and a client who took configuration off the schedule is told every coverage
    has a copy, under a row saying one has none."""
    schedule = tuple(one for one in SCHEDULE if one.coverage is not Coverage.CONFIGURATION)
    backups = without(Coverage.CONFIGURATION)
    ok = [rehearsed()]

    service_level(PROFILE, verifications=ok, backups=backups, now=NOW, schedule=schedule)
    shown = built(backups, ok, schedule=schedule)

    assert shown.assurance is Assurance.RECOVERABLE
    row = next(one for one in shown.copies if one.coverage is Coverage.CONFIGURATION)
    assert [fact.source for fact in row.facts] == [Source.UNKNOWN, Source.UNKNOWN]
    assert not row.within_objective
    assert "every coverage has a copy" not in shown.answer.says.lower()
    assert "the schedule copies" in shown.answer.says


def test_a_verdict_over_no_rows_at_all_is_nothing_copied_rather_than_recoverable():
    """`panel` always hands `assurance_of` a row per coverage, so this is a caller assembling
    rows by hand and passing none. A verdict over no rows is not about an install, and the one
    answer it must not be is the reassuring one, which `Panel` refuses on the same grounds.

    The sibling is the same rehearsal over the rows `copy_states` builds, which is recoverable.

    Delete this and a caller that forgot to pass the copies gets a tick."""
    ok = [rehearsed()]
    rows = copy_states(fresh(), profile=PROFILE, now=NOW)

    assert assurance_of((), ok, objective=OBJECTIVE, now=NOW) is Assurance.NOTHING_COPIED
    assert assurance_of(rows, ok, objective=OBJECTIVE, now=NOW) is Assurance.RECOVERABLE


# --- clocks that disagree ------------------------------------------------------------------
def test_a_naive_now_is_refused_rather_than_deciding_staleness_at_this_machines_offset():
    """Delete this and a panel asked in local time decides whether a rehearsal is stale by
    however many hours this server sits from UTC."""
    rows = copy_states(fresh(), profile=PROFILE, now=NOW)

    with pytest.raises(RecoveryViewError, match="naive"):
        assurance_of(rows, [rehearsed()], objective=OBJECTIVE, now=NOW.replace(tzinfo=None))
    assert assurance_of(rows, [rehearsed()], objective=OBJECTIVE, now=NOW) in SETTLED


def test_a_copy_restoring_to_a_moment_that_has_not_happened_stops_the_panel():
    """Two clocks disagree, and an exposure computed past that copy reads smaller than the
    truth. A screen that fails to draw sends somebody to look; one drawing a healthier number
    does not. The sibling is a copy restoring to this very instant, which draws.

    Delete this and a server whose clock runs an hour fast shows every copy as current."""
    ahead = [
        a_copy(one, seconds_ago=-60) if one is Coverage.DATABASE else a_copy(one)
        for one in Coverage
    ]
    level = [
        a_copy(one, seconds_ago=0) if one is Coverage.DATABASE else a_copy(one) for one in Coverage
    ]

    with pytest.raises(RecoveryError, match="has not happened"):
        built(ahead, [rehearsed()])
    assert built(level, [rehearsed()]).copies[0].measured_exposure_seconds == 0


# --- one row -------------------------------------------------------------------------------
def test_a_row_cannot_hold_an_exposure_without_a_copy_or_a_copy_without_an_exposure():
    """Both are a row lying about itself in a direction a renderer would draw: an exposure on
    nothing reads as a copy that exists, and a copy with no exposure renders as never copied.
    A recovery point of nothing is a promise no copy keeps. The sibling is the row
    `copy_states` builds from the same copy.

    Delete this and a hand-assembled row can say a coverage nothing copied is half an hour
    behind."""
    copy = a_copy(Coverage.DATABASE)
    row: dict[str, Any] = {
        "coverage": Coverage.DATABASE,
        "newest": copy,
        "scheduled_every_seconds": 60,
        "measured_exposure_seconds": 1_800.0,
        "objective_seconds": OBJECTIVE.rpo_seconds,
    }

    with pytest.raises(RecoveryViewError, match="measurement of nothing"):
        CopyState(**{**row, "newest": None})
    with pytest.raises(RecoveryViewError, match="render as never copied"):
        CopyState(**{**row, "measured_exposure_seconds": None})
    with pytest.raises(RecoveryViewError, match="no copy can ever be inside"):
        CopyState(**{**row, "objective_seconds": 0})

    built_row = copy_states([copy], profile=PROFILE, now=NOW)[0]
    assert built_row == CopyState(**row)
    assert built_row.within_objective


# --- what a client reads -------------------------------------------------------------------
def test_every_answer_has_both_sentences_and_names_nothing_only_this_repository_has():
    """A member added without an answer raises a `KeyError` at the moment somebody opens the
    screen, on an install in whichever state nobody thought about. And the sentences are for
    somebody with a server and no source tree, so none names a module, a function or a task.

    Delete this and one state is a stack trace, or a sentence telling a client to look at a
    function name."""
    assert set(ANSWERS) == set(Assurance)
    for answer, pair in ANSWERS.items():
        assert isinstance(pair, Answer), answer
        for sentence in (pair.says, pair.what_to_do):
            assert sentence.strip(), answer
            assert "brain." not in sentence, answer
            assert "`" not in sentence, answer
            assert "_" not in sentence, answer
            words = sentence.replace(".", " ").split()
            assert [word for word in words if word[:1] == "M" and word[1:2].isdigit()] == []


def test_the_field_is_named_the_way_the_screen_registry_describes_it():
    """`LAST_VERIFIED_FACT` is held against the registry's own sentence for this screen rather
    than against itself, so renaming the field without the menu, or the menu without the
    field, fails here. The two row labels are held apart for the same reason: equal, every
    coverage shows two statements under one name and the intention reads as the fact.

    Delete this and the heading somebody checks before deciding not to worry drifts from the
    name the menu promised them."""
    registered = screen("recovery")

    assert LAST_VERIFIED_FACT in registered.purpose
    assert registered.read.requires.value == "read:backup"
    assert len({SCHEDULE_FACT, NEWEST_FACT}) == 2


def test_nothing_in_this_module_reads_a_clock_opens_a_connection_or_touches_a_file():
    """**Every observation is a parameter, and this is that claim checked.** The interesting
    states are an install with no copies and a bucket with a truncated record, and neither is
    reachable through a module that opens an object store or reads the process clock.

    Delete this and the first "just read it directly" passes every other test in this file."""
    reaching = {
        "asyncio",
        "boto3",
        "httpx",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "shutil",
        "socket",
        "sqlalchemy",
        "subprocess",
        "time",
        "urllib",
    }
    imported: list[str] = []
    clocks: list[str] = []
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.extend(one.name for one in node.names)
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        called = node.func if isinstance(node, ast.Call) else None
        if isinstance(called, ast.Attribute) and called.attr in {"now", "utcnow", "today"}:
            clocks.append(called.attr)

    assert "brain.ops.recovery" in imported, "the walk read no imports, so it proves nothing"
    assert [one for one in imported if one.split(".")[0] in reaching] == []
    assert clocks == []
