"""A backup, a restore that was attempted, and the one that was verified.

The distinction those three words carry is the whole of M30.3 and it is the thing that
disappears first when somebody is implementing a runner in a hurry. So most of these tests
are refusals: a drill that did not verify carrying a recovery time, a verification that
claims success and lists reasons it failed, a copy of zero bytes, a restore into the live
database. Every one of them is a state a real backup script produces on a bad night.

The positive cases sit beside them deliberately. A guard tested only by its refusals is
satisfied by a function that refuses everything, and a recovery layer that refuses every
drill is a recovery layer nobody runs twice.

Task ids: M30.3.3, M30.3.4, M30.3.6, M30.3.7, M30.3.8, M30.3.10, M30.3.11
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.recovery import (
    DRILL_INTERVAL_DAYS,
    LONGEST_MONTH_DAYS,
    RETENTION_LADDER,
    SCHEDULE,
    Alert,
    Backup,
    Check,
    CheckRun,
    Coverage,
    Destination,
    Drill,
    KeyHolder,
    Ladder,
    Method,
    RecoveryError,
    Scheduled,
    Severity,
    Verification,
    alerts,
    backup_policy_gaps,
    destination_gaps,
    drill_due,
    exposure_seconds,
    last_verified_restore,
    latest,
    scheduled_exposure_seconds,
    verification_of,
    worst_scheduled_exposure_seconds,
)
from brain.ops.reliability import RECOVERY_OBJECTIVES, RecoveryObjective, recovery_objective
from brain.ops.retention import BACKUP_RETENTION_DAYS

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _backup(
    *,
    backup_id: str = "b1",
    coverage: Coverage = Coverage.DATABASE,
    method: Method = Method.FULL,
    finished: datetime | None = None,
    reaches: datetime | None = None,
    size_bytes: int = 4096,
) -> Backup:
    """A plausible copy. Every field a test cares about is a keyword, the rest are defaults."""
    ended = NOW - timedelta(minutes=30) if finished is None else finished
    return Backup(
        backup_id=backup_id,
        coverage=coverage,
        method=method,
        destination="off-host object store",
        started_at=ended - timedelta(minutes=5),
        finished_at=ended,
        recoverable_to=ended if reaches is None else reaches,
        size_bytes=size_bytes,
    )


def _drill(*, passing: tuple[Check, ...] = tuple(Check), minutes: int = 40) -> Drill:
    """A drill that ran the named checks and passed them, taking `minutes`."""
    return Drill(
        backup_id="b1",
        started_at=NOW - timedelta(minutes=minutes),
        finished_at=NOW,
        into_scratch=True,
        checks=tuple(
            CheckRun(check=one, passed=True, detail="asked and answered") for one in passing
        ),
    )


# ------------------------------------------------------------ attempted against verified
def test_a_drill_that_did_not_verify_records_no_recovery_time() -> None:
    """**The distinction the whole module exists for, and the one an implementation loses
    first.**

    The obvious version times every drill and stores the elapsed seconds. An operator then
    plans an incident around forty minutes taken from a run that restored in forty minutes
    and failed its permission canary, which produced a database answering every question for
    everybody. That drill recovered nothing.

    Delete this and the field is filled on every attempt, because the number is available and
    filling it looks like completeness."""
    failed = Drill(
        backup_id="b1",
        started_at=NOW - timedelta(minutes=40),
        finished_at=NOW,
        into_scratch=True,
        checks=(
            CheckRun(check=Check.SCHEMA_COMPLETE, passed=True, detail="every schema present"),
            CheckRun(check=Check.SMOKE_QUERY, passed=True, detail="the known row came back"),
            CheckRun(
                check=Check.PERMISSION_CANARY,
                passed=False,
                detail="a restricted field answered a principal who may not read it",
            ),
        ),
    )

    verdict = verification_of(failed)

    assert verdict.verified is False
    assert verdict.rto_seconds is None
    assert any("permission_canary" in one for one in verdict.shortfalls)


def test_a_verified_drill_records_the_time_from_the_restore_starting_to_the_last_check() -> None:
    """The positive half, and the measurement is deliberately the whole drill rather than
    the load.

    A recovery time is time until the system can be used, and a copy nobody has questioned
    yet cannot be used. Measuring only the restore would report a number that excludes the
    checks the restore is worthless without.

    Delete this and the module refuses everything and measures nothing, which passes every
    refusal test above."""
    verdict = verification_of(_drill(minutes=40))

    assert verdict.verified is True
    assert verdict.shortfalls == ()
    assert verdict.rto_seconds == 40 * 60


def test_a_check_that_did_not_run_is_not_a_check_that_passed() -> None:
    """A drill missing its permission canary and a drill whose permission canary failed are
    different faults with different people to talk to: one is a misconfigured runner and the
    other is a restore that produced an open database. Both are shortfalls and the sentences
    say which.

    Delete this and a runner that silently skips a check produces a verified restore, which
    is the worst possible output of this module."""
    partial = _drill(passing=(Check.SCHEMA_COMPLETE, Check.SMOKE_QUERY))

    verdict = verification_of(partial)

    assert verdict.verified is False
    assert any(
        "did not run" in one and Check.PERMISSION_CANARY.value in one for one in verdict.shortfalls
    )


def test_every_check_this_module_declares_is_required() -> None:
    """There are no optional checks, and that is asserted against the enum rather than
    against a count.

    A member added to `Check` and left out of `REQUIRED_CHECKS` would be a check that can be
    declared, run, failed, and ignored by the verdict, which is worse than not having it.

    Delete this and the required set becomes a subset the first time a check is inconvenient."""
    from brain.ops.recovery import REQUIRED_CHECKS

    assert set(REQUIRED_CHECKS) == set(Check)
    assert len(REQUIRED_CHECKS) == len(set(REQUIRED_CHECKS))


def test_the_permission_canary_is_what_catches_a_restore_that_lost_its_policies() -> None:
    """**Why three checks rather than the two the leaf names, argued as a test.**

    A restore that brought back every row and none of the row-level security policies passes
    a schema check and passes any smoke query anybody would write, because the data is there
    and it is correct. It answers everything, to everybody. Only the canary sees it.

    Delete this and the canary looks like the least important of the three, because it is the
    one that passes on a healthy system with nothing interesting to say."""
    open_copy = Drill(
        backup_id="b1",
        started_at=NOW - timedelta(minutes=10),
        finished_at=NOW,
        into_scratch=True,
        checks=(
            CheckRun(check=Check.SCHEMA_COMPLETE, passed=True, detail="every schema present"),
            CheckRun(check=Check.SMOKE_QUERY, passed=True, detail="the known row came back"),
            CheckRun(check=Check.PERMISSION_CANARY, passed=False, detail="a refusal did not"),
        ),
    )

    assert verification_of(open_copy).verified is False


def test_a_restore_into_anything_but_a_scratch_target_is_refused() -> None:
    """A weekly automated restore that can be pointed at the live database is a scheduled
    outage, and the misconfiguration lives in the runner rather than here.

    Refused in the value class because that is the guard that survives the runner being
    rewritten, which is the same argument `brain.ops.storage.Bucket.public_read` makes.

    Delete this and the field is a comment."""
    with pytest.raises(RecoveryError, match="scratch"):
        Drill(
            backup_id="b1",
            started_at=NOW - timedelta(minutes=10),
            finished_at=NOW,
            into_scratch=False,
            checks=(),
        )


def test_a_verification_cannot_claim_success_and_carry_reasons_it_failed() -> None:
    """Four states that would let a reader believe more than was proved, all refused at
    construction so no renderer has to decide which field to trust.

    Delete this and `Verification` becomes a record a caller can assemble by hand, and the
    caller assembling it is the runner that just failed."""
    with pytest.raises(RecoveryError, match="disagree"):
        Verification(
            backup_id="b1",
            attempted_at=NOW,
            verified=True,
            rto_seconds=60.0,
            shortfalls=("the canary failed",),
        )
    with pytest.raises(RecoveryError, match="says nothing about why"):
        Verification(
            backup_id="b1", attempted_at=NOW, verified=False, rto_seconds=None, shortfalls=()
        )
    with pytest.raises(RecoveryError, match="one number the drill exists to produce"):
        Verification(
            backup_id="b1", attempted_at=NOW, verified=True, rto_seconds=None, shortfalls=()
        )
    with pytest.raises(RecoveryError, match="recovery time"):
        Verification(
            backup_id="b1",
            attempted_at=NOW,
            verified=False,
            rto_seconds=2400.0,
            shortfalls=("the canary failed",),
        )


def test_a_drill_that_ran_one_check_twice_is_refused() -> None:
    """Which result the verdict uses would then depend on the order the runs happen to be
    in, and the two would not both be there unless they disagreed.

    Delete this and a runner that retries a failing check until it passes produces a verified
    restore."""
    with pytest.raises(RecoveryError, match="same check twice"):
        Drill(
            backup_id="b1",
            started_at=NOW - timedelta(minutes=10),
            finished_at=NOW,
            into_scratch=True,
            checks=(
                CheckRun(check=Check.SMOKE_QUERY, passed=False, detail="nothing came back"),
                CheckRun(check=Check.SMOKE_QUERY, passed=True, detail="something came back"),
            ),
        )


def test_a_check_that_says_nothing_about_what_it_asked_is_refused() -> None:
    """A failure arrives as a red light with no bulb behind it, and the person reading it at
    3am has to go and find the runner's logs.

    Delete this and the shortfall sentences become the check's own name repeated."""
    with pytest.raises(RecoveryError, match="says nothing"):
        CheckRun(check=Check.SMOKE_QUERY, passed=False, detail="  ")


def test_the_last_verified_restore_does_not_move_because_somebody_tried_and_failed() -> None:
    """The field a console labels "last verified restore" is the one somebody checks before
    deciding not to worry, and the natural implementation sorts everything by attempt time.

    Delete this and a week of failing drills makes the panel look healthier every night."""
    good = verification_of(_drill(minutes=30))
    bad = Verification(
        backup_id="b2",
        attempted_at=NOW + timedelta(days=1),
        verified=False,
        rto_seconds=None,
        shortfalls=("the canary failed",),
    )

    found = last_verified_restore([good, bad])

    assert found is not None
    assert found.backup_id == "b1"
    assert last_verified_restore([bad]) is None
    assert last_verified_restore([]) is None


# ------------------------------------------------------------------- what a copy is
def test_a_copy_of_no_bytes_is_refused() -> None:
    """A dump command that exits zero having written nothing is the commonest silent backup
    failure there is, and it is invisible in every listing that shows a timestamp.

    Delete this and the object with the newest timestamp in the bucket is empty and the
    console says the backup is fresh."""
    with pytest.raises(RecoveryError, match="0 bytes"):
        _backup(size_bytes=0)


def test_a_copy_that_is_not_continuously_archived_cannot_restore_past_its_own_end() -> None:
    """Only continuous archiving keeps arriving after the run that produced it. A full copy
    claiming to reach further is a field somebody filled with `now` instead of the run's end,
    and it makes the exposure read as zero for ever.

    Delete this and every backup can claim to be current."""
    ended = NOW - timedelta(hours=6)

    with pytest.raises(RecoveryError, match="continuous archiving"):
        _backup(method=Method.FULL, finished=ended, reaches=NOW)

    archived = _backup(method=Method.CONTINUOUS_WAL, finished=ended, reaches=NOW)

    assert archived.recoverable_to == NOW


def test_the_newest_copy_is_the_one_that_reaches_furthest_forward() -> None:
    """**The reason `recoverable_to` exists as a field separate from `finished_at`.**

    Last week's full backup plus this minute's archived segments reaches further than
    yesterday's incremental, so ordering by when the run finished picks the wrong copy and
    reports a day of exposure on a database that is a minute behind.

    Delete this and `latest` gets rewritten to sort by `finished_at`, which reads more
    naturally and is wrong exactly when continuous archiving is doing its job."""
    older_run_reaching_further = _backup(
        backup_id="wal",
        method=Method.CONTINUOUS_WAL,
        finished=NOW - timedelta(days=7),
        reaches=NOW - timedelta(minutes=1),
    )
    newer_run_reaching_less_far = _backup(
        backup_id="incremental",
        method=Method.INCREMENTAL,
        finished=NOW - timedelta(hours=20),
    )

    found = latest([newer_run_reaching_less_far, older_run_reaching_further], Coverage.DATABASE)

    assert found is not None
    assert found.backup_id == "wal"


def test_a_copy_reaching_into_the_future_is_refused_rather_than_clamped() -> None:
    """The cause is a clock disagreement between whatever wrote the copy and this process,
    and clamping the exposure to zero reports a healthier figure than the truth, which is the
    one direction an operator must never be lied to in.

    Delete this and the obvious `max(0, ...)` makes a skewed clock look like a perfect
    recovery point."""
    ahead = _backup(
        method=Method.CONTINUOUS_WAL,
        finished=NOW - timedelta(hours=1),
        reaches=NOW + timedelta(hours=1),
    )

    with pytest.raises(RecoveryError, match="has not happened"):
        exposure_seconds([ahead], Coverage.DATABASE, now=NOW)


def test_a_coverage_with_no_copy_has_no_exposure_rather_than_a_large_one() -> None:
    """`None` and a big number are different answers. A big number is a backup that is late;
    `None` is a coverage nothing has ever copied, and the remedy is different.

    `alerts` is what turns the second into a line somebody reads.

    Delete this and the caller of `exposure_seconds` invents a sentinel."""
    assert exposure_seconds([], Coverage.OBJECT_STORE, now=NOW) is None
    assert exposure_seconds([_backup()], Coverage.DATABASE, now=NOW) == 30 * 60
    assert latest([], Coverage.DATABASE) is None


def test_a_naive_timestamp_anywhere_near_a_recovery_point_is_refused() -> None:
    """An exposure computed from a naive time is wrong by whatever this machine's offset
    happens to be, which on a server in one timezone and a laptop in another is a different
    wrong number in each place.

    Delete this and a recovery point objective is met or missed depending on where the
    process ran."""
    with pytest.raises(RecoveryError, match="naive"):
        Backup(
            backup_id="b1",
            coverage=Coverage.DATABASE,
            method=Method.FULL,
            destination="off-host",
            started_at=datetime(2026, 9, 8, 11, 0),
            finished_at=NOW,
            recoverable_to=NOW,
            size_bytes=10,
        )
    with pytest.raises(RecoveryError, match="naive"):
        exposure_seconds([_backup()], Coverage.DATABASE, now=datetime(2026, 9, 8, 12, 0))
    with pytest.raises(RecoveryError, match="naive"):
        drill_due(last_verified_at=None, now=datetime(2026, 9, 8, 12, 0))


# ------------------------------------------------------------------ the drill schedule
def test_a_system_that_has_never_verified_a_restore_is_due_for_a_drill_now() -> None:
    """`None` is due. A system with no record is not between drills, it is one whose backups
    have never been read back, and treating an absent record as "not yet time" is how that
    state lasts a year.

    Delete this and the state this repository is actually in reads as up to date."""
    assert drill_due(last_verified_at=None, now=NOW) is True
    assert drill_due(last_verified_at=NOW - timedelta(days=1), now=NOW) is False
    assert drill_due(last_verified_at=NOW - timedelta(days=DRILL_INTERVAL_DAYS), now=NOW) is True


def test_the_drill_interval_is_shorter_than_the_window_a_copy_is_kept_for() -> None:
    """**The interval is anchored to something outside itself and this is the anchor.**

    An interval longer than the retention window means a copy can be written, kept, expired
    and deleted without anybody having read it back once, so the rehearsal never touches the
    copies it is meant to be proving.

    Delete this and the interval becomes a number, and lengthening it to a month during a
    busy quarter is a one-character change nothing objects to."""
    assert DRILL_INTERVAL_DAYS < BACKUP_RETENTION_DAYS
    assert backup_policy_gaps(drill_interval_days=BACKUP_RETENTION_DAYS) != ()
    assert any(
        "without anybody having read it back" in one
        for one in backup_policy_gaps(drill_interval_days=BACKUP_RETENTION_DAYS)
    )


# ------------------------------------------------------------------ the retention ladder
def test_the_retention_ladder_outlives_the_horizon_every_erasure_certificate_promises() -> None:
    """**The finding that stops M30.3.5 being implemented, asserted rather than written in a
    commit message nobody re-reads.**

    Thirty daily, twelve weekly and twelve monthly copies keeps a backup up to 372 days old.
    `brain.ops.erasure.backup_horizon` adds `BACKUP_RETENTION_DAYS` to a completed deletion
    and a certificate states that date as the moment the data is beyond backup reach. Pruning
    to this ladder without moving that number does not make a certificate late, it makes it
    false, on a document written for somebody who asked to be forgotten.

    Delete this and the ladder gets implemented, because it is what the leaf asks for and the
    conflict is two modules away."""
    reach = RETENTION_LADDER.horizon_days()

    assert reach > BACKUP_RETENTION_DAYS
    assert reach == 12 * LONGEST_MONTH_DAYS
    assert any("beyond backup reach" in one for one in backup_policy_gaps(ladder=RETENTION_LADDER))


def test_a_ladder_inside_the_horizon_is_reported_as_no_conflict() -> None:
    """The positive half, and it is also the shape of the fix: a ladder whose longest rung
    fits inside the window the certificates promise raises nothing.

    Delete this and the conflict check can become unconditional, which is a red light that
    can never go out and therefore one somebody switches off."""
    inside = Ladder(daily=7, weekly=1, monthly=0)

    assert inside.horizon_days() <= BACKUP_RETENTION_DAYS
    assert not any("beyond backup reach" in one for one in backup_policy_gaps(ladder=inside))


def test_the_ladder_horizon_is_its_longest_rung_and_not_the_sum_of_them() -> None:
    """The rungs overlap: yesterday's copy is a daily and, one day a week, also a weekly. So
    adding them counts one backup up to three times and produces a horizon beyond anything
    retained, which would make the conflict above look larger than it is.

    Delete this and the arithmetic behind a legal claim about deleted data is unchecked."""
    assert Ladder(daily=30, weekly=12, monthly=12).horizon_days() == 372
    assert Ladder(daily=400, weekly=1, monthly=1).horizon_days() == 400
    assert Ladder(daily=0, weekly=0, monthly=1).horizon_days() == LONGEST_MONTH_DAYS
    # Twelve weeks is eighty-four days, asserted as the number rather than as twelve times
    # the module's own constant, which would compare it against itself. Written after a
    # mutation of `DAYS_IN_A_WEEK` to 1 survived: the monthly rung dominates the declared
    # ladder, so nothing here reached the weekly arithmetic at all.
    assert Ladder(daily=1, weekly=12, monthly=0).horizon_days() == 84


def test_a_ladder_that_keeps_nothing_is_refused() -> None:
    """It is a deletion policy wearing a backup's name, and it is what a configuration form
    submits when every field is left blank.

    Delete this and an install can be configured to retain no copies at all with the whole
    backup pipeline reporting success."""
    with pytest.raises(RecoveryError, match="keeps nothing"):
        Ladder(daily=0, weekly=0, monthly=0)
    with pytest.raises(RecoveryError, match="not a retention policy"):
        Ladder(daily=-1, weekly=0, monthly=1)


# --------------------------------------------------------------------- the destinations
def test_a_copy_on_the_same_host_as_the_original_is_reported() -> None:
    """The failure that destroys the original destroys the copy in the same second, and it
    is the configuration everybody starts with because it is the one that works first time.

    Delete this and an off-host destination becomes advice."""
    same_box = Destination(
        name="local disk",
        covers=frozenset(Coverage),
        off_host=False,
        key_held_by=KeyHolder.CLIENT,
        because="it was already mounted",
    )

    assert any("same host" in one for one in destination_gaps([same_box]))


def test_a_key_this_platform_holds_and_a_copy_with_no_key_are_both_reported() -> None:
    """Two different failures with two different sentences. An unencrypted copy carries every
    field the permission layer protects with none of the permission layer attached. A copy
    encrypted with our key makes the client's records ours to lose and ours to be compelled
    for.

    Delete this and encryption becomes a boolean and the question of who holds the key stops
    being asked at all."""
    ours = Destination(
        name="our bucket",
        covers=frozenset(Coverage),
        off_host=True,
        key_held_by=KeyHolder.PLATFORM,
        because="convenient for support",
    )
    none = Destination(
        name="plain bucket",
        covers=frozenset(Coverage),
        off_host=True,
        key_held_by=KeyHolder.NOBODY,
        because="nothing was configured",
    )

    assert any("key this platform holds" in one for one in destination_gaps([ours]))
    assert any("unencrypted" in one for one in destination_gaps([none]))


def test_a_coverage_nothing_copies_anywhere_is_reported() -> None:
    """The state this repository is actually in for all three: the bucket exists and nothing
    writes to it. The finding is per coverage rather than one summary, so the day the
    database is covered and the object store is not, the list says which.

    Delete this and a destination set covering one third of the system reports clean."""
    database_only = Destination(
        name="off-host",
        covers=frozenset({Coverage.DATABASE}),
        off_host=True,
        key_held_by=KeyHolder.CLIENT,
        because="the database first",
    )
    found = destination_gaps([database_only])

    assert any(Coverage.OBJECT_STORE.value in one for one in found)
    assert any(Coverage.CONFIGURATION.value in one for one in found)
    assert not any(Coverage.DATABASE.value in one for one in found)


def test_a_destination_set_that_holds_reports_nothing() -> None:
    """The positive case. Off host, encrypted with the client's key, covering all three
    kinds.

    Delete this and `destination_gaps` can start refusing everything, which passes every test
    above and makes the check useless."""
    good = Destination(
        name="client's off-host object store",
        covers=frozenset(Coverage),
        off_host=True,
        key_held_by=KeyHolder.CLIENT,
        because="a different building and a key we cannot read",
    )

    assert destination_gaps([good]) == ()


def test_a_destination_covering_nothing_is_refused() -> None:
    """It is a copy of nothing, and it is what an empty multi-select produces.

    Delete this and the coverage check above is satisfied by a destination that copies
    nothing but names every kind."""
    with pytest.raises(RecoveryError, match="copy of nothing"):
        Destination(
            name="somewhere",
            covers=frozenset(),
            off_host=True,
            key_held_by=KeyHolder.CLIENT,
            because="not decided yet",
        )


# ------------------------------------------------------------------------- the schedule
def test_the_declared_schedule_can_meet_every_declared_recovery_objective() -> None:
    """The arithmetic that makes a recovery point objective a promise rather than a wish.

    Every coverage is scheduled, and the tightest profile's objective is at least the slowest
    interval on the schedule. The `full` profile sits exactly on that boundary, which is the
    point: tightening it means changing the schedule in the same edit.

    Delete this and an objective can be tightened for a client with no copy being taken any
    more often."""
    slowest = worst_scheduled_exposure_seconds()

    assert slowest is not None
    assert scheduled_exposure_seconds(Coverage.DATABASE) == 60
    assert min(one.rpo_seconds for one in RECOVERY_OBJECTIVES) >= slowest
    standing = backup_policy_gaps()

    assert len(standing) == 1, f"a second policy finding appeared: {standing}"
    assert "beyond backup reach" in standing[0], (
        "the retention ladder's conflict with the erasure horizon is the only finding this "
        "module is meant to be standing on, and something else is now failing too"
    )


def test_an_objective_the_schedule_cannot_meet_is_reported() -> None:
    """**A recovery point objective is a promise about the slowest copy, not the fastest.**

    The database is archived every minute and the object store is snapshotted hourly, so a
    profile promising five minutes is promising something true of the database and false of
    every uploaded document. The check is against the slowest interval for that reason.

    Delete this and the objectives are checked against continuous archiving, which every one
    of them passes, and a client is promised minutes on their files."""
    tight = (
        RecoveryObjective(
            profile="full",
            rpo_seconds=300,
            rto_seconds=3600,
            because="the database can do it",
        ),
    )
    found = backup_policy_gaps(objectives=tight)

    assert any("slowest thing on the schedule" in one for one in found)


def test_a_coverage_nothing_is_scheduled_to_copy_is_reported() -> None:
    """An unbounded exposure and a slow one are different findings, and only one of them is a
    number, which is why `worst_scheduled_exposure_seconds` leaves this to `backup_policy_gaps`.

    Delete this and dropping the configuration snapshot from the schedule reads as an
    improvement, because the worst interval gets better."""
    database_only = tuple(one for one in SCHEDULE if one.coverage is Coverage.DATABASE)
    found = backup_policy_gaps(schedule=database_only)

    assert any(Coverage.OBJECT_STORE.value in one and "by hand" in one for one in found)
    assert scheduled_exposure_seconds(Coverage.OBJECT_STORE, database_only) is None


def test_a_scheduled_copy_on_no_interval_is_refused() -> None:
    """Zero is how "whenever somebody runs it" gets written into a field that wants a number,
    and it would make the schedule's exposure arithmetic report perfection.

    Delete this and the recovery point check divides a promise by a copy nothing takes."""
    with pytest.raises(RecoveryError, match="not a schedule"):
        Scheduled(
            coverage=Coverage.DATABASE,
            method=Method.FULL,
            every_seconds=0,
            because="manual for now",
        )


# --------------------------------------------------------------------------- alerting
def test_a_failed_verification_is_louder_than_an_aged_backup() -> None:
    """**Louder is a comparison rather than a convention, and this is why it is an IntEnum.**

    An aged backup says the last stretch of work is not copied anywhere. A failed
    verification says nothing held is known to be readable, which is a statement about every
    copy rather than about one of them. The loud one is sorted first because an operator
    triaging at 3am reads down.

    Delete this and the two severities are two strings and the ordering is whatever the list
    happened to be built in."""
    assert Severity.VERIFICATION_FAILED > Severity.BACKUP_AGED

    failed = Verification(
        backup_id="b1",
        attempted_at=NOW,
        verified=False,
        rto_seconds=None,
        shortfalls=("permission_canary ran and did not pass",),
    )
    found = alerts(backups=[], verifications=[failed], profile="lite", now=NOW)

    assert found[0].severity is Severity.VERIFICATION_FAILED
    assert len(found) == 1 + len(Coverage)


def test_a_backup_older_than_the_profile_objective_raises_an_alert_and_a_fresh_one_does_not() -> (
    None
):
    """Both halves, because a guard tested only by its refusals is satisfied by a function
    that alerts on everything, and an alert that always fires is one nobody reads.

    The threshold is the profile's own objective rather than a constant here, so a client on
    a tighter profile is alerted sooner without a second number existing.

    Delete this and the comparison can be inverted with the suite green."""
    lite = recovery_objective("lite")
    stale = _backup(
        method=Method.CONTINUOUS_WAL,
        finished=NOW - timedelta(seconds=lite.rpo_seconds + 60),
        reaches=NOW - timedelta(seconds=lite.rpo_seconds + 60),
    )
    everything = [
        stale,
        _backup(backup_id="obj", coverage=Coverage.OBJECT_STORE),
        _backup(backup_id="cfg", coverage=Coverage.CONFIGURATION),
    ]

    aged = alerts(backups=everything, verifications=[], profile="lite", now=NOW)

    assert len(aged) == 1
    assert aged[0].severity is Severity.BACKUP_AGED
    assert aged[0].coverage is Coverage.DATABASE

    fresh = [_backup(), *everything[1:]]

    assert alerts(backups=fresh, verifications=[], profile="lite", now=NOW) == ()


def test_a_coverage_with_no_copy_at_all_alerts_at_the_aged_level() -> None:
    """An absent copy and a late copy are the same fact with the same remedy: there is no
    copy of the last stretch of work. Splitting them into two severities gives an operator
    two thresholds where there is one problem.

    This is the state the repository is in today, so it is the alert that would fire on every
    install if anything ran the check.

    Delete this and the never-backed-up case falls through the age comparison silently,
    because there is no age to compare."""
    found = alerts(backups=[], verifications=[], profile="lite", now=NOW)

    assert len(found) == len(Coverage)
    assert all(one.severity is Severity.BACKUP_AGED for one in found)
    assert all("no copy of" in one.text for one in found)


def test_a_tighter_profile_alerts_on_a_copy_the_looser_one_accepts() -> None:
    """The threshold comes from the profile, which is what makes one alerting rule serve
    three installs.

    Delete this and the objective can stop being read, with the alert firing on a constant
    that happens to match one profile."""
    behind = timedelta(seconds=recovery_objective("full").rpo_seconds + 60)
    copies = [
        _backup(
            backup_id=name,
            coverage=kind,
            method=Method.CONTINUOUS_WAL,
            finished=NOW - behind,
            reaches=NOW - behind,
        )
        for name, kind in (
            ("db", Coverage.DATABASE),
            ("obj", Coverage.OBJECT_STORE),
            ("cfg", Coverage.CONFIGURATION),
        )
    ]

    assert alerts(backups=copies, verifications=[], profile="lite", now=NOW) == ()
    assert len(alerts(backups=copies, verifications=[], profile="full", now=NOW)) == len(Coverage)


def test_an_alert_with_no_text_is_refused() -> None:
    """It wakes somebody to look at a blank line.

    Delete this and an alert can be constructed from a formatting expression that produced
    nothing."""
    with pytest.raises(RecoveryError, match="no text"):
        Alert(severity=Severity.BACKUP_AGED, coverage=Coverage.DATABASE, text="")


# ------------------------------------------- the refusals a first mutation run found unwatched
#
# Every test below was written after `.scratch/m30_guard_audit.py` mutated each `if` in
# `brain.ops.recovery` and reported it surviving. A guard nothing can reach is not a guard,
# and the twelve here were the difference between a module that refuses these states and a
# module that says it does.
#
# Blank strings are tested as `" "` as well as `""`, because a value arriving from a
# configuration form or a scheduler's YAML is whitespace far more often than it is empty, and
# a bare falsiness check passes whitespace straight through.
def test_a_backup_with_no_id_or_a_blank_one_is_refused() -> None:
    """A copy nothing can name cannot be named by a restore, an alert or a drill, so every
    downstream sentence about it reads "backup '' did not verify".

    Delete this and an id built from an empty template is stored and reported."""
    for name in ("", "   "):
        with pytest.raises(RecoveryError, match="no id"):
            _backup(backup_id=name)


def test_a_backup_that_finished_before_it_started_is_refused() -> None:
    """Two clocks, or a duration subtracted the wrong way. Either way the copy's window is
    negative and the exposure computed from it is nonsense in the flattering direction.

    Delete this and a run whose end timestamp was taken from a different machine is stored."""
    ended = NOW - timedelta(hours=2)

    with pytest.raises(RecoveryError, match="finished before it started"):
        Backup(
            backup_id="b1",
            coverage=Coverage.DATABASE,
            method=Method.FULL,
            destination="off-host",
            started_at=NOW,
            finished_at=ended,
            recoverable_to=ended,
            size_bytes=10,
        )


def test_a_backup_that_restores_to_a_moment_before_it_began_reading_is_refused() -> None:
    """A copy of something older than itself, which is what a snapshot of a replica that
    stopped replicating looks like from here: the run is recent and the data is not.

    The check is against `started_at` rather than `finished_at`, because a copy legitimately
    reaches back to the moment it began reading and never further.

    Delete this and a stalled replica's snapshot reports the exposure of a fresh one."""
    ended = NOW - timedelta(hours=1)

    with pytest.raises(RecoveryError, match="before it began"):
        Backup(
            backup_id="stale",
            coverage=Coverage.DATABASE,
            method=Method.FULL,
            destination="off-host",
            started_at=ended,
            finished_at=ended + timedelta(minutes=5),
            recoverable_to=ended - timedelta(days=3),
            size_bytes=10,
        )


def test_a_drill_with_no_id_or_a_blank_one_is_refused() -> None:
    """A drill that cannot say which copy it read has verified nothing in particular, and it
    is exactly what a runner produces when the id is looked up after the restore rather than
    before it.

    Delete this and a verified restore can name no backup, which is the panel's whole
    content."""
    for name in ("", "   "):
        with pytest.raises(RecoveryError, match="which copy"):
            Drill(
                backup_id=name,
                started_at=NOW - timedelta(minutes=10),
                finished_at=NOW,
                into_scratch=True,
                checks=(),
            )


def test_a_drill_with_a_naive_timestamp_or_a_negative_duration_is_refused() -> None:
    """The recovery time is subtracted from these two fields and is the number an operator
    plans an incident around. A naive one is wrong by this machine's offset and a reversed
    pair is negative, and `Verification` refuses the negative afterwards, which is the second
    guard rather than the first.

    Delete this and a drill timed across a daylight-saving boundary reports an hour it did
    not take."""
    with pytest.raises(RecoveryError, match="naive"):
        Drill(
            backup_id="b1",
            started_at=datetime(2026, 9, 8, 11, 0),
            finished_at=NOW,
            into_scratch=True,
            checks=(),
        )
    with pytest.raises(RecoveryError, match="negative recovery time"):
        Drill(
            backup_id="b1",
            started_at=NOW,
            finished_at=NOW - timedelta(minutes=10),
            into_scratch=True,
            checks=(),
        )


def test_a_verification_carrying_a_negative_recovery_time_is_refused() -> None:
    """The last of the four consistency checks and the only one about the number rather than
    about the flags. A negative recovery time is a subtraction that went the wrong way, and
    it would render as a drill that finished before it started.

    Delete this and the only thing standing between a reversed subtraction and a console is
    a renderer's formatting."""
    with pytest.raises(RecoveryError, match="recovered in"):
        Verification(
            backup_id="b1", attempted_at=NOW, verified=True, rto_seconds=-60.0, shortfalls=()
        )


def test_a_drill_schedule_compared_against_a_naive_last_verified_time_is_refused() -> None:
    """`drill_due` takes two moments and subtracts them. An aware `now` and a naive last
    verification compare by accident: Python refuses the subtraction with a `TypeError`,
    which arrives as a crash in a scheduler rather than as a sentence saying which value was
    wrong.

    Delete this and a stored timestamp read back without its offset stops the weekly drill
    with a stack trace."""
    with pytest.raises(RecoveryError, match="naive last verified"):
        drill_due(last_verified_at=datetime(2026, 9, 1, 12, 0), now=NOW)


def test_a_schedule_that_copies_nothing_has_no_worst_exposure_rather_than_zero() -> None:
    """An empty schedule is the state before anybody has configured one, and the arithmetic
    over it has no answer: the maximum of nothing is not zero, and zero here would read as a
    system whose slowest copy is instantaneous.

    `backup_policy_gaps` is what turns that `None` into three sentences saying nothing is
    copied, which is why this returns rather than raising.

    Delete this and an unconfigured install reports that every recovery point objective is
    met."""
    assert worst_scheduled_exposure_seconds(()) is None
    assert backup_policy_gaps(schedule=()) != ()
    assert len([one for one in backup_policy_gaps(schedule=()) if "by hand" in one]) == len(
        Coverage
    )


def test_a_destination_with_no_name_or_no_reason_is_refused() -> None:
    """A destination with no name cannot be found by whoever needs it at 3am, and one with no
    reason is the one that gets pointed somewhere cheaper, because nobody can say what the
    current choice was protecting.

    `brain.ops.storage.Bucket` requires the same prose for the same reason: an unexplained
    lifecycle rule is one that gets relaxed and never restored.

    Delete this and both fields become optional in practice, filled by whichever form
    submitted last."""
    for name in ("", "   "):
        with pytest.raises(RecoveryError, match="no name"):
            Destination(
                name=name,
                covers=frozenset(Coverage),
                off_host=True,
                key_held_by=KeyHolder.CLIENT,
                because="somewhere else",
            )
    for reason in ("", "   "):
        with pytest.raises(RecoveryError, match="states no reason"):
            Destination(
                name="off-host",
                covers=frozenset(Coverage),
                off_host=True,
                key_held_by=KeyHolder.CLIENT,
                because=reason,
            )


def test_a_scheduled_copy_with_no_reason_for_its_interval_is_refused() -> None:
    """An unexplained interval is the one that gets lengthened, because the person doing it
    has nothing to weigh the change against.

    Delete this and the hourly object-store snapshot becomes daily during a busy week and the
    tightest profile's recovery point objective is quietly unmet."""
    for reason in ("", "   "):
        with pytest.raises(RecoveryError, match="states no reason"):
            Scheduled(
                coverage=Coverage.OBJECT_STORE,
                method=Method.SNAPSHOT,
                every_seconds=3600,
                because=reason,
            )
