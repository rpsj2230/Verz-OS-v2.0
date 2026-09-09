"""The handover pack: what it refuses to state, and what it will not hand over without.

The subject of this file is a set of documents, which is the kind of deliverable that is
usually tested by checking a string contains a heading. It is not tested that way here. Every
section of the pack is an object derived from a register, and every test below asserts either
on that object or on the arithmetic that produced it.

Two constants are anchored to their own WBS leaf sentences rather than to themselves, using
`brain.status.leaf_sentences`. `Responsibility` names three things and the leaf names the same
three; `REVIEW_AFTER_DAYS` is thirty and the leaf says thirty. A test that imported either and
compared it against itself would be green for every value it could hold, which is the trap
`CLAUDE.md` records three authors falling into in one afternoon.

Task ids: M30.5.4, M37.4.2.2, M37.4.2.4, M37.4.3.1, M37.4.3.2, M37.4.3.3, M37.4.3.5
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from brain import launch
from brain.console.screens import SCREENS, Screen
from brain.launch import (
    REVIEW_AFTER_DAYS,
    LaunchError,
    Owner,
    Responsibility,
    assemble,
    owner_gaps,
    pack_gaps,
    playbook_gaps,
    review_gaps,
    screen_runbook_gaps,
    service_level,
    subprocessors,
)
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.ops.recovery import SCHEDULE, Backup, Coverage, Method, Scheduled, Verification
from brain.ops.reliability import (
    MATRIX,
    RECOVERY_OBJECTIVES,
    RecoveryObjective,
    matrix_gaps,
)
from brain.status import leaf_sentences

#: The leaf sentences, read from the compiled work breakdown so a constant here is asserted
#: against the sentence that specifies it rather than against itself.
LEAF_SENTENCES = leaf_sentences(Path(__file__).resolve().parents[2] / "docs" / "wbs.json")

LAUNCH_DAY = date(2026, 3, 2)
NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def a_verified_restore(seconds: float, *, at: datetime = NOW) -> Verification:
    """A drill that verified, through the constructor's own refusals."""
    return Verification(
        backup_id="bk_1", attempted_at=at, verified=True, rto_seconds=seconds, shortfalls=()
    )


def a_failed_restore(*, at: datetime = NOW) -> Verification:
    """A drill that did not verify, and therefore carries no recovery time."""
    return Verification(
        backup_id="bk_0",
        attempted_at=at,
        verified=False,
        rto_seconds=None,
        shortfalls=("the permission canary did not run",),
    )


def an_objective(profile: str, *, rpo: int, rto: int) -> RecoveryObjective:
    """One profile's promise, built through `RecoveryObjective`'s own validators."""
    return RecoveryObjective(
        profile=profile,
        rpo_seconds=rpo,
        rto_seconds=rto,
        because="a figure written for this test and argued nowhere else",
    )


def three_owners() -> tuple[Owner, ...]:
    """One named person against each responsibility."""
    return tuple(
        Owner(responsibility=one, name=f"Owner of {one.value}", contact=f"{one.value}@example.test")
        for one in Responsibility
    )


def every_screen_covered() -> dict[str, str]:
    """A runbook for every console screen there is."""
    return {one.key: f"how to work the {one.key} screen" for one in SCREENS}


#: The instant every recovery figure below is measured against.
#:
#: 2999 for the reason CLAUDE.md records: a fixture with a plausible date in it is a clock and
#: it goes off on a morning nobody chose. `brain.ops.recovery.exposure_seconds` refuses a copy
#: that restores to a moment after `now`, so the copies below are built relative to this.
MEASURED_AT = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)


def a_copy(coverage: Coverage, *, seconds_ago: float) -> Backup:
    """One copy of one coverage, that recent. Full rather than continuous, because only
    continuous archiving may restore past the moment it finished and these are simple."""
    when = MEASURED_AT - timedelta(seconds=seconds_ago)
    return Backup(
        backup_id=f"{coverage.value}-{seconds_ago:.0f}",
        coverage=coverage,
        method=Method.FULL,
        destination="s3://backups",
        started_at=when - timedelta(seconds=1),
        finished_at=when,
        recoverable_to=when,
        size_bytes=1_048_576,
    )


def copies(seconds_ago: float = 60.0) -> tuple[Backup, ...]:
    """One copy of every coverage the schedule covers, all equally recent.

    Every coverage, because the refusal is per coverage: an estate that copies its database
    hourly and has never copied its configuration has an unbounded exposure on the second, and
    a helper that supplied only the first would make every test below pass for the wrong
    reason.
    """
    return tuple(a_copy(one, seconds_ago=seconds_ago) for one in Coverage)


# --- what we promise (M30.5.4, M37.4.2.2) ------------------------------------------------


def test_a_recovery_point_the_backup_schedule_cannot_deliver_is_refused_not_stated() -> None:
    """M30.5.4, M37.4.2.2. **A recovery point objective is a promise about the slowest copy**,
    so a stated figure tighter than the interval anything actually runs at is a promise the
    estate is already failing on the day the client signs it.

    The objective is passed in rather than taken from `RECOVERY_OBJECTIVES`, so this stays
    true when somebody retunes the real figures: what is asserted is the comparison, not
    today's numbers.

    Delete this and a service level statement renders whatever the objective says, and the
    only way anybody finds out is a restore that loses more than the contract allows."""
    tight = (an_objective("standard", rpo=60, rto=14_400),)

    with pytest.raises(LaunchError, match="slowest copy on the schedule"):
        service_level(
            "standard",
            backups=copies(),
            now=MEASURED_AT,
            verifications=[a_verified_restore(100.0)],
            schedule=SCHEDULE,
            objectives=tight,
        )


def test_an_estate_that_holds_no_copies_at_all_cannot_state_a_recovery_point() -> None:
    """**This is the finding item 46 turned up and it made the statement signable on nothing.**

    Until 2026-09-10 the recovery point was checked against `SCHEDULE` alone, and `SCHEDULE`
    is a declaration of what ought to be copied that nothing had ever executed. Measured that
    day: `worst_scheduled_exposure_seconds()` returned 3600 against `lite`'s promise of 86400,
    so the refusal passed comfortably while the estate held no copies whatsoever. A schedule
    is an intention and a copy is a fact.

    Reported as unbounded rather than as a large number, because those are different findings:
    a slow copy is a figure somebody can compare against a promise, and no copy at all is not
    a figure. `worst_scheduled_exposure_seconds` draws the same distinction for the schedule.

    Delete this and a client can sign a recovery point on a system that has never been copied,
    which is the document doing the opposite of its job."""
    with pytest.raises(LaunchError, match="it is unbounded"):
        service_level(
            "standard",
            backups=[],
            now=MEASURED_AT,
            verifications=[a_verified_restore(100.0)],
        )


def test_a_coverage_the_schedule_covers_and_nothing_has_copied_is_named() -> None:
    """The per-coverage half. An estate copying its database hourly and never copying its
    configuration has an unbounded exposure on the second, and a check that looked at the
    newest copy of anything would report the estate as healthy.

    An install restored with last month's realm and policies is a different install, which is
    the sentence `SCHEDULE` already carries about configuration.

    Delete this and one well-copied coverage vouches for every other."""
    only_the_database = [a_copy(Coverage.DATABASE, seconds_ago=60.0)]

    with pytest.raises(LaunchError, match="nothing has ever copied"):
        service_level(
            "standard",
            backups=only_the_database,
            now=MEASURED_AT,
            verifications=[a_verified_restore(100.0)],
        )


def test_copies_that_have_fallen_behind_the_promise_are_refused_however_good_the_schedule_is() -> (
    None
):
    """The other way the two disagree, and it is the ordinary failure rather than the
    dramatic one: everything is scheduled, everything is configured, and the copies stopped a
    week ago. The schedule still says hourly and the estate is a week behind.

    Asserted against a `standard` objective of four hours with copies eight hours old, so the
    schedule's answer would pass and the measurement does not.

    **The recovery time in this fixture is deliberately not the recovery point, and a mutation
    is why.** Both were four hours in the first version, so comparing the measured exposure
    against the recovery time instead of the recovery point produced the same verdict and no
    test could tell the two apart. A fixture whose two figures happen to be equal cannot
    distinguish them, which is the same trap CLAUDE.md records about a constant compared
    against itself. Twenty-four hours here, and eight hours of exposure sits inside it.

    Delete this and a backup job that silently stopped is invisible to the one document whose
    job is to promise it works."""
    fits = (an_objective("standard", rpo=14_400, rto=86_400),)

    with pytest.raises(LaunchError, match="restores to"):
        service_level(
            "standard",
            backups=copies(seconds_ago=28_800.0),
            now=MEASURED_AT,
            verifications=[a_verified_restore(100.0)],
            objectives=fits,
        )


def test_copies_inside_the_promise_are_stated_rather_than_refused() -> None:
    """The positive case, and without it a refusal that refused everything would pass all
    three tests above. A guard tested only by what it stops is satisfied by one that stops
    everything, which here would be a system that can never hand over a pack.

    Delete this and the fourth refusal can be made unconditional with the suite green."""
    fits = (an_objective("standard", rpo=14_400, rto=14_400),)

    stated = service_level(
        "standard",
        backups=copies(seconds_ago=600.0),
        now=MEASURED_AT,
        verifications=[a_verified_restore(100.0)],
        objectives=fits,
    )

    assert stated.rpo_seconds == 14_400


def test_a_coverage_nothing_schedules_is_not_asked_for_a_copy() -> None:
    """The asymmetry that keeps this from being red on arrival. `worst_scheduled_exposure_seconds`
    ignores a coverage nothing schedules, and reports it through `backup_policy_gaps` instead,
    because an unbounded exposure and an unscheduled one are different findings. The measured
    check follows the same rule: it asks about the coverages the schedule covers, so removing
    a coverage from the schedule removes it from both questions at once rather than turning a
    silent gap into a refusal nobody can act on.

    Delete this and narrowing the schedule makes the statement harder to produce rather than
    easier, which is backwards."""
    database_only = tuple(one for one in SCHEDULE if one.coverage is Coverage.DATABASE)
    fits = (an_objective("standard", rpo=14_400, rto=14_400),)

    stated = service_level(
        "standard",
        backups=[a_copy(Coverage.DATABASE, seconds_ago=600.0)],
        now=MEASURED_AT,
        verifications=[a_verified_restore(100.0)],
        schedule=database_only,
        objectives=fits,
    )

    assert stated.profile == "standard"


def test_a_recovery_point_the_schedule_does_deliver_is_stated_with_the_interval_beside_it() -> None:
    """The sibling of the refusal above: the same call with a schedule that keeps up produces
    a statement, and the statement carries the measured interval as well as the promise.

    Both figures, because a service level that states only the target lets a client read the
    target as an observation. The gap between `rpo_seconds` and `scheduled_exposure_seconds`
    is the margin, and it is the client's to see.

    Delete this and a guard that refuses everything passes the test above."""
    fits = (an_objective("standard", rpo=7_200, rto=14_400),)
    hourly = (
        Scheduled(
            coverage=Coverage.DATABASE,
            method=Method.INCREMENTAL,
            every_seconds=3_600,
            because="hourly, so the promise has an hour of margin in this test",
        ),
    )

    stated = service_level(
        "standard",
        backups=copies(),
        now=MEASURED_AT,
        verifications=[a_verified_restore(100.0)],
        schedule=hourly,
        objectives=fits,
    )

    assert stated.rpo_seconds == 7_200
    assert stated.scheduled_exposure_seconds == 3_600
    assert stated.profile == "standard"


def test_a_recovery_time_no_drill_has_ever_measured_is_refused() -> None:
    """**An unmeasured recovery time is a guess in a contract.** `RECOVERY_OBJECTIVES` states
    a target per profile and nothing on this estate measures one except a restore drill, so a
    statement produced before any drill has verified is a number somebody chose.

    A failed drill is passed rather than an empty list, which is the case that would slip
    through a bare emptiness check: `last_verified_restore` exists precisely because an
    attempted restore is not a verified one.

    Delete this and a client signs a recovery time on an install whose backups have never
    been restored."""
    with pytest.raises(LaunchError, match="guess in a contract"):
        service_level(
            "standard", backups=copies(), now=MEASURED_AT, verifications=[a_failed_restore()]
        )


def test_a_recovery_time_the_last_verified_drill_exceeded_is_refused() -> None:
    """The third promise, and the one that is invisible to anybody reading the schedule: the
    figure is achievable in principle, the drills run, and the last one took longer than the
    contract allows.

    Delete this and the statement says four hours while the evidence in the same estate says
    five, and the two are never compared."""
    slow = (an_objective("standard", rpo=14_400, rto=3_600),)

    with pytest.raises(LaunchError, match="last verified restore took"):
        service_level(
            "standard",
            backups=copies(),
            now=MEASURED_AT,
            verifications=[a_verified_restore(7_200.0)],
            objectives=slow,
        )


def test_a_statement_carries_the_drills_own_measurement_and_the_date_it_was_taken() -> None:
    """The positive case for all three refusals at once, and the assertion that the
    measurement on the statement is the drill's rather than the target repeated.

    Two drills, the later one slower, so a statement that reported the best figure it could
    find rather than the most recent would show 60 and this fails.

    Delete this and `measured_rto_seconds` can be filled from `rto_seconds` and every refusal
    above still passes."""
    fits = (an_objective("standard", rpo=14_400, rto=14_400),)
    older = a_verified_restore(60.0, at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = a_verified_restore(9_000.0, at=datetime(2026, 2, 1, tzinfo=UTC))

    stated = service_level(
        "standard",
        backups=copies(),
        now=MEASURED_AT,
        verifications=[older, newer],
        objectives=fits,
    )

    assert stated.measured_rto_seconds == 9_000.0
    assert stated.measured_at == datetime(2026, 2, 1, tzinfo=UTC)
    assert stated.rto_seconds == 14_400


def test_a_statement_for_an_install_that_copies_nothing_is_refused() -> None:
    """An install with no backup schedule at all has an unbounded recovery point, and
    unbounded is not a large number: `worst_scheduled_exposure_seconds` returns `None` for it
    rather than something a comparison would quietly pass.

    Delete this and an empty schedule produces a statement, because `None > 14400` was never
    evaluated and the objective was rendered as though it held.

    Separate from the too-slow case above because the two are different findings and only one
    of them is a number, which is the distinction `brain.ops.recovery` already makes."""
    with pytest.raises(LaunchError, match="nothing is scheduled to be copied"):
        service_level(
            "standard",
            backups=copies(),
            now=MEASURED_AT,
            verifications=[a_verified_restore(100.0)],
            schedule=(),
        )


def test_every_declared_profile_can_state_a_service_level_against_the_real_schedule() -> None:
    """The three real profiles against the real schedule, which is the check that the figures
    in `RECOVERY_OBJECTIVES` and the intervals in `SCHEDULE` were written to agree.

    This is the test that goes red if somebody lengthens a backup interval, and that is its
    whole purpose: the two live in different modules and nothing else compares them.

    Delete this and the schedule can be relaxed to daily while three signed agreements
    continue to promise an hour."""
    for objective in RECOVERY_OBJECTIVES:
        stated = service_level(
            objective.profile,
            backups=copies(),
            now=MEASURED_AT,
            verifications=[a_verified_restore(1.0)],
        )
        assert stated.scheduled_exposure_seconds <= stated.rpo_seconds


# --- who else sees it all (M37.4.2.4) ----------------------------------------------------


def test_the_subprocessor_list_names_every_provider_a_key_is_held_for_and_no_other() -> None:
    """M37.4.2.4. The list is derived from the keys the install holds, so a provider that
    exists as a slot and has no key is not on it: it cannot receive anything.

    Two providers configured out of three, so a function returning every declared slot passes
    nothing here.

    Delete this and the agreement names a provider the client never sends anything to, which
    is a smaller error than the other direction and is still a legal document that is wrong."""
    named = subprocessors(["anthropic", "openai"])

    assert [one.slug for one in named] == ["anthropic", "openai"]
    assert all(one.purpose for one in named)


def test_a_key_configured_for_a_provider_no_slot_declares_is_refused() -> None:
    """A credential nobody argued about. `PROVIDER_SLOTS` is closed on purpose, and its own
    comment says a provider that can be configured but was never discussed is a provider
    whose key nobody decided to trust.

    A refusal rather than a silently dropped row, because dropping it produces an agreement
    that does not name a party the install is sending questions to.

    Delete this and an install with a fourth key hands over a three-name subprocessor list."""
    with pytest.raises(LaunchError, match="no provider slot declares"):
        subprocessors(["anthropic", "some_other_model_host"])


def test_an_install_configured_with_no_model_provider_cannot_produce_a_list() -> None:
    """An install with no key cannot answer a question, so an empty subprocessor list would
    be a statement that this system processes nothing with anybody, true only until somebody
    sets a key and never revisited.

    Delete this and the pack assembles for an install that cannot answer, and the client
    signs a schedule with no parties on it."""
    with pytest.raises(LaunchError, match="cannot answer a question"):
        subprocessors([])


def test_a_provider_named_on_the_agreement_with_no_purpose_beside_it_is_refused() -> None:
    """`ProviderSlot.description` defaults to empty, because a slot is a key location and does
    not know it will end up as a schedule to a processing agreement. Here it does, and a name
    with nothing beside it is what the client's lawyer asks about.

    Built through `ProviderSlot`'s own validators so this is a real slot rather than a stub,
    and whitespace rather than empty, because a description of `" "` is what somebody types
    to get past a form.

    Delete this and the agreement carries a bare slug."""
    blank = (ProviderSlot(slug="anthropic", env_var="ANTHROPIC_API_KEY", description=" "),)

    with pytest.raises(LaunchError, match="no purpose"):
        subprocessors(["anthropic"], slots=blank)


def test_the_subprocessor_rows_come_from_the_provider_register_and_are_not_written_here() -> None:
    """The structural half of M37.4.2.4, and the reason the section exists at all: adding a
    fourth model provider must change the agreement.

    Asserted against `PROVIDER_SLOTS` rather than against three names, so a slot added to
    that register appears here without anybody editing this file, and a purpose reworded
    there is reworded on the agreement.

    Delete this and the list can be typed out, and the day a provider is added the document
    is false with nothing going red."""
    named = subprocessors([one.slug for one in PROVIDER_SLOTS])

    assert [one.slug for one in named] == [one.slug for one in PROVIDER_SLOTS]
    assert [one.purpose for one in named] == [one.description for one in PROVIDER_SLOTS]


# --- a runbook per screen (M37.4.3.1) ----------------------------------------------------


def test_a_console_screen_with_no_runbook_is_a_gap_in_the_pack() -> None:
    """M37.4.3.1. The screens are read off `brain.console.screens.SCREENS`, so the
    thirty-fifth screen arrives as a gap rather than as a screen the client was handed no
    instructions for.

    Delete this and the completeness check is a count somebody updates by hand."""
    short = every_screen_covered()
    dropped = SCREENS[0].key
    del short[dropped]

    assert any(dropped in one for one in screen_runbook_gaps(short))
    assert screen_runbook_gaps(every_screen_covered()) == ()


def test_a_runbook_for_a_screen_that_does_not_exist_is_a_gap_because_it_reads_as_coverage() -> None:
    """The other direction, and the worse one. A missing runbook is obvious to whoever looks
    for it; a runbook for a screen that was renamed sits in the pack looking like coverage,
    and the count of runbooks matches the count of screens.

    Delete this and a rename leaves the pack the same size and one screen short."""
    stale = every_screen_covered()
    stale["a_screen_that_was_renamed"] = "how to work a screen that is not there"

    findings = screen_runbook_gaps(stale)

    assert any("does not exist" in one for one in findings)


def test_an_empty_runbook_is_a_gap_and_not_an_entry() -> None:
    """An entry present with nothing in it is how a completeness check gets satisfied by
    somebody working down a list of screens.

    Whitespace as well as empty, because `" "` passes a bare falsiness check and is what a
    text area posts when it was clicked into and left.

    Delete this and the pack can be completed by pressing space thirty-four times."""
    for nothing in ("", " "):
        blank = every_screen_covered()
        blank[SCREENS[0].key] = nothing

        assert any("empty" in one for one in screen_runbook_gaps(blank))


def test_the_screens_are_read_from_the_console_register_and_not_from_a_list_here() -> None:
    """Asserted on the signature as well as the behaviour. The wrong version of this section
    arrives as a `screen_keys` parameter added so a client can be handed a shorter pack, and
    behaviour alone would keep passing on the day it lands.

    Delete this and the runbook check becomes a comparison against whatever the caller
    happened to pass, which is always complete."""
    taken = inspect.signature(screen_runbook_gaps).parameters

    assert "screens" in taken
    assert taken["screens"].default is SCREENS
    assert all(isinstance(one, Screen) for one in taken["screens"].default)


# --- a playbook per failure mode (M37.4.3.2) ---------------------------------------------


def test_the_playbook_completeness_check_is_the_reliability_matrixs_own_and_not_a_copy() -> None:
    """M37.4.3.2. `brain.ops.reliability.MATRIX` is the incident playbook already: it carries
    what fails, what it presents as, what it blocks, whether the work can be retried and what
    to do about it. A second completeness check here would be a second register, and the two
    would disagree the first time a component was added to `brain.ops.wiring.COMPONENTS`.

    Asserted on the source rather than only on the answer, because a reimplementation that
    happens to agree today passes an equality check and is exactly the thing being refused.

    Delete this and the pack grows its own list of components."""
    body = inspect.getsource(launch.playbook_gaps)

    assert "return matrix_gaps(" in body
    assert playbook_gaps() == matrix_gaps()


def test_a_component_with_no_failure_mode_stops_the_pack() -> None:
    """The behaviour the delegation buys: a component nothing has written a failure mode for
    is a component whose first outage is written up during the incident.

    Passed in rather than mutating the register, so this test says nothing about whether the
    real matrix is complete today, which is `test_reliability`'s question.

    Delete this and the pack hands over a playbook with a hole in it."""
    findings = playbook_gaps(rows=(), components=("db",))

    assert any("db" in one for one in findings)


def test_the_playbook_handed_over_is_the_matrix_in_declaration_order() -> None:
    """The positive case. The pack carries the rows themselves, not a count of them, because
    a pack that says "34 runbooks and 11 playbooks" is a pack nobody can act from.

    Delete this and the section can become a number."""
    assert launch.playbooks() == MATRIX
    assert launch.playbooks(rows=MATRIX[:1]) == MATRIX[:1]


# --- who runs it afterwards (M37.4.3.3) --------------------------------------------------


def test_the_three_responsibilities_are_the_ones_the_leaf_names() -> None:
    """M37.4.3.3 says knowledge, grants and connectors. The enum says the same three, and
    this is the assertion that keeps them the same three.

    Read from the compiled work breakdown rather than from a tuple written here, so the
    vocabulary is anchored to the sentence that specifies it instead of to itself. A test
    comparing `set(Responsibility)` against three names written in this file would be green
    for any three names somebody chose.

    Delete this and a fourth responsibility can be invented, or one dropped, and the pack
    still claims the leaf."""
    sentence = LEAF_SENTENCES["M37.4.3.3"].lower()

    assert len(Responsibility) == 3
    for one in Responsibility:
        assert one.value in sentence, f"{one.value} is not in the leaf that specifies this"


def test_a_responsibility_with_no_owner_and_one_with_two_are_both_findings() -> None:
    """Two names against grants means each of them believes the other is reviewing the queue.
    No name against knowledge is the same outcome reached from the other side.

    Delete this and the pack hands over with a review queue nobody has been asked to work."""
    everyone = three_owners()
    grants = Owner(responsibility=Responsibility.GRANTS, name="Second", contact="s@example.test")

    missing = owner_gaps(
        [one for one in everyone if one.responsibility is not Responsibility.GRANTS]
    )
    doubled = owner_gaps([*everyone, grants])

    assert any("grants" in one and "nobody" in one for one in missing)
    assert any("grants" in one and "2 owners" in one for one in doubled)
    assert owner_gaps(everyone) == ()


def test_one_person_may_own_all_three_which_is_what_a_small_client_looks_like() -> None:
    """The asymmetry in `A_RESPONSIBILITY_TWO_PEOPLE_OWN_IS_A_RESPONSIBILITY_NEITHER_OWNS`,
    and the positive case that stops the check above being satisfied by refusing everything.

    Delete this and a uniqueness check on names slips in, and a ten-person client cannot
    complete the pack."""
    alone = tuple(
        Owner(responsibility=one, name="The one administrator", contact="admin@example.test")
        for one in Responsibility
    )

    assert owner_gaps(alone) == ()


def test_an_owner_with_no_name_or_no_way_to_reach_them_cannot_be_constructed() -> None:
    """ "The finance team" is not a person, and the point of the section is that there is
    somebody to ask. Refused in the constructor rather than in `owner_gaps`, so an owner that
    exists is an owner that can be contacted.

    Whitespace as well as empty for both fields, because that is what a form posts.

    Delete this and the pack is complete with three blank rows in it."""
    for nothing in ("", " "):
        with pytest.raises(LaunchError, match="owned by nobody named"):
            Owner(responsibility=Responsibility.KNOWLEDGE, name=nothing, contact="a@example.test")
        with pytest.raises(LaunchError, match="no way to ask them"):
            Owner(responsibility=Responsibility.KNOWLEDGE, name="A person", contact=nothing)


# --- the date it is looked at again (M37.4.3.5) ------------------------------------------


def test_the_review_window_is_the_figure_the_leaf_states() -> None:
    """M37.4.3.5 says a thirty-day review. `REVIEW_AFTER_DAYS` says thirty, and it is asserted
    against the leaf and against a literal written outside the module, never against itself.

    Delete this and the window can be changed to ninety in the module and every boundary test
    below moves with it."""
    assert REVIEW_AFTER_DAYS == 30
    assert "thirty-day" in LEAF_SENTENCES["M37.4.3.5"].lower()


def test_a_review_booked_beyond_the_window_is_a_finding_and_the_last_day_is_not() -> None:
    """The boundary, with literal dates rather than arithmetic on the constant, so this test
    moves if the constant does.

    Day thirty passes, day thirty-one does not. On-the-day is allowed because a review booked
    for exactly the horizon is the review the leaf asks for.

    Delete this and a review booked for day ninety completes the pack, and by then the
    workarounds people invented in week one are the process."""
    assert review_gaps(launched_on=date(2026, 3, 2), review_booked_for=date(2026, 4, 1)) == ()
    assert review_gaps(launched_on=date(2026, 3, 2), review_booked_for=date(2026, 4, 2)) != ()


def test_a_review_booked_on_or_before_launch_day_reviews_nothing() -> None:
    """A date in the past satisfies a check that only looks at the upper bound, and a review
    on launch day itself reviews an install that has not been used.

    Delete this and a pack completes with a review booked for last month."""
    assert review_gaps(launched_on=LAUNCH_DAY, review_booked_for=LAUNCH_DAY) != ()
    assert review_gaps(launched_on=LAUNCH_DAY, review_booked_for=date(2026, 2, 1)) != ()


# --- the pack (M37.4.1 handover) ---------------------------------------------------------


def test_an_incomplete_pack_raises_with_every_finding_rather_than_the_first() -> None:
    """A pack that renders five of six sections gets handed over, and the sixth is discovered
    by whoever needed it during the incident it was written for. So assembly raises, and it
    raises with everything at once: a caller fixing one finding per run does not find the
    second one until the first is fixed.

    Two independent gaps, an unowned responsibility and a missing runbook, so an exception
    carrying only the first fails here.

    Delete this and the pack is fixed one round trip at a time, or worse, handed over."""
    short = every_screen_covered()
    del short[SCREENS[0].key]

    with pytest.raises(LaunchError) as raised:
        assemble(
            "standard",
            backups=copies(),
            now=MEASURED_AT,
            configured_providers=["anthropic"],
            verifications=[a_verified_restore(1.0)],
            owners=[
                one for one in three_owners() if one.responsibility is not Responsibility.GRANTS
            ],
            screen_runbooks=short,
            launched_on=LAUNCH_DAY,
            review_booked_for=date(2026, 3, 20),
        )

    message = str(raised.value)
    assert "grants" in message
    assert SCREENS[0].key in message


def test_the_arithmetic_refusals_run_before_the_missing_paperwork() -> None:
    """A client whose backup schedule cannot meet their own recovery point should hear that,
    not that a runbook is missing. The service level and the subprocessor list refuse in
    their own constructors with the figures in the message, and `assemble` calls them first.

    The pack here is otherwise complete except for the runbooks, so a version collecting
    every finding in section order would report the runbook and not the promise.

    Delete this and the ordering is whatever the field order happens to be."""
    with pytest.raises(LaunchError, match="slowest copy on the schedule"):
        assemble(
            "standard",
            backups=copies(),
            now=MEASURED_AT,
            configured_providers=["anthropic"],
            verifications=[a_verified_restore(1.0)],
            owners=three_owners(),
            screen_runbooks={},
            launched_on=LAUNCH_DAY,
            review_booked_for=date(2026, 3, 20),
            objectives=(an_objective("standard", rpo=60, rto=14_400),),
        )


def test_a_complete_pack_carries_every_section_as_objects_and_not_as_prose() -> None:
    """The positive case, and the assertion that the pack is structured. A `Pack` holding
    rendered markdown was the obvious shape and is wrong: the pack would be a string, and
    every test above could only assert on substrings of it, which is how two tests in this
    repository came to be satisfied by their own docstrings.

    Delete this and every refusal above is satisfied by a function that refuses everything."""
    pack = assemble(
        "standard",
        backups=copies(),
        now=MEASURED_AT,
        configured_providers=["anthropic", "openai"],
        verifications=[a_verified_restore(1.0)],
        owners=three_owners(),
        screen_runbooks=every_screen_covered(),
        launched_on=LAUNCH_DAY,
        review_booked_for=date(2026, 3, 20),
    )

    assert pack.service_level.profile == "standard"
    assert [one.slug for one in pack.subprocessors] == ["anthropic", "openai"]
    assert len(pack.owners) == len(Responsibility)
    assert set(pack.screen_runbooks) == {one.key for one in SCREENS}
    assert pack.playbooks == MATRIX
    assert pack.review_booked_for > pack.launched_on


def test_pack_gaps_answers_the_same_question_without_raising() -> None:
    """A console screen showing what is outstanding before launch day needs the findings, not
    an exception, and it must not have to build a service level statement to get them.

    Delete this and the pre-launch screen calls `assemble` in a try block, which means it
    cannot show anything until the arithmetic sections pass."""
    assert (
        pack_gaps(
            owners=three_owners(),
            screen_runbooks=every_screen_covered(),
            launched_on=LAUNCH_DAY,
            review_booked_for=date(2026, 3, 20),
        )
        == ()
    )
    assert (
        pack_gaps(
            owners=(),
            screen_runbooks=every_screen_covered(),
            launched_on=LAUNCH_DAY,
            review_booked_for=date(2026, 3, 20),
        )
        != ()
    )
