"""Switching the old system off: the order, the grants, the jobs and the last copy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.migration.decommission import (
    Decommission,
    DecommissionError,
    FinalBackup,
    Revocation,
    ScheduledJob,
    credentials_outstanding,
    decommission_gaps,
    jobs_outstanding,
)
from brain.ops.retention import BACKUP_RETENTION_DAYS

#: Pinned far from any wall clock, for the reason CLAUDE.md gives about fixtures with dates.
CUT_OVER = datetime(2030, 6, 1, tzinfo=UTC)
LATER = CUT_OVER + timedelta(days=1)
LATER_STILL = CUT_OVER + timedelta(days=2)


def a_record(**kw: object) -> Decommission:
    fields: dict[str, object] = {
        "cut_over_at": CUT_OVER,
        "read_only_at": LATER,
        "archived_at": LATER_STILL,
        "final_backup": FinalBackup(backup_id="b1", taken_at=LATER, verified=True),
    }
    fields.update(kw)
    return Decommission(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------- the order it happens in
def test_making_the_old_system_read_only_before_the_cutover_is_refused() -> None:
    """M37.1.4.1 is read-only and then archived, and the ordering is the whole of it.
    **A system made read-only during a comparison period stops answering the questions the
    period exists to ask**, so the read-only moment waits for the cutover.

    Delete this and the two can be recorded in either order, and a parallel run that was
    quietly one-sided reports as a clean decommission."""
    with pytest.raises(DecommissionError, match="before the cutover"):
        a_record(read_only_at=CUT_OVER - timedelta(hours=1))


def test_archiving_a_system_that_was_never_made_read_only_is_refused() -> None:
    """An archive of a system somebody can still write to is already out of date, and nothing
    about the archive says so.

    Delete this and the archive step can be reported alone, which is the step people report
    because it is the one with a file at the end of it."""
    with pytest.raises(DecommissionError, match="never made read-only"):
        a_record(read_only_at=None)


def test_archiving_before_the_read_only_moment_is_refused() -> None:
    """The same rule with both moments present and the wrong way round, which is what a form
    filled in from memory a week later produces.

    Delete this and the ordering check passes on any record where both fields are set, which
    is every record anybody finishes."""
    with pytest.raises(DecommissionError, match="the wrong way round"):
        a_record(read_only_at=LATER_STILL, archived_at=LATER)


def test_a_record_in_the_right_order_is_accepted() -> None:
    """The positive case for all three.

    Delete this and the ordering rules can be tightened until no decommission is
    representable."""
    record = a_record()

    assert record.read_only_at == LATER
    assert record.archived_at == LATER_STILL


# ------------------------------------------------------------------- the credentials
def test_a_revocation_naming_no_connector_is_refused() -> None:
    """Delete this and the blank branch is unreachable."""
    with pytest.raises(DecommissionError, match="names no connector"):
        Revocation(connector="  ")


def test_a_confirmation_with_nothing_to_confirm_is_refused() -> None:
    """A verified revocation nobody asked for is a record of somebody ticking the second box
    without the first, and it is the shape a bulk edit leaves behind.

    Delete this and the register can be cleared by setting one field on every row."""
    with pytest.raises(DecommissionError, match="nobody asked for it"):
        Revocation(connector="drive", verified_at=LATER)


def test_a_confirmation_dated_before_the_request_is_refused() -> None:
    """Two timestamps that cannot both be true. It is what a copied row looks like, and it
    would otherwise sit in the record as a completed revocation.

    Delete this and the pair of dates is never compared, so nothing here would ever notice."""
    with pytest.raises(DecommissionError, match="before it was asked"):
        Revocation(connector="drive", requested_at=LATER_STILL, verified_at=LATER)


def test_a_grant_nobody_asked_about_and_one_nobody_confirmed_are_separate_findings() -> None:
    """M37.1.4.2 revokes a credential on every connector the old system held, and the two
    ways that is unfinished are separate findings. **They reach different people.** A grant
    nobody has asked about needs whoever holds the account; a grant asked about and never
    confirmed needs whoever asked. Reported as one number they reach nobody, because "three
    outstanding" is not a task.

    The unasked ones come first, because they are the ones nothing is in motion for.

    Delete this and cancelling a subscription reads as revoking the grants under it, which is
    the mistake this whole step exists for."""
    findings = credentials_outstanding(
        (
            Revocation(connector="calendar", requested_at=LATER),
            Revocation(connector="drive"),
            Revocation(connector="sheets", requested_at=LATER, verified_at=LATER_STILL),
        )
    )

    assert findings == (
        "drive: nobody has asked for this grant to be withdrawn",
        f"calendar: withdrawal asked for at {LATER} and never confirmed",
    )


def test_a_confirmed_revocation_is_not_outstanding() -> None:
    """The positive case.

    Delete this and `credentials_outstanding` can be written to report every connector."""
    confirmed = Revocation(connector="drive", requested_at=LATER, verified_at=LATER_STILL)

    assert credentials_outstanding((confirmed,)) == ()


# --------------------------------------------------------------------- the scheduled jobs
def test_a_job_with_no_name_is_refused() -> None:
    """Delete this and the blank branch is unreachable."""
    with pytest.raises(DecommissionError, match="has no name"):
        ScheduledJob(name=" ")


def test_watching_a_job_that_was_never_disabled_is_refused() -> None:
    """An observation window on a job still running on its schedule measures nothing about
    whether it stopped, and it would satisfy every check below.

    Delete this and a job can be reported verified stopped while its schedule is untouched."""
    with pytest.raises(DecommissionError, match="was never disabled"):
        ScheduledJob(name="nightly sync", watched_until=LATER)


def test_a_window_that_closes_before_the_disable_is_refused() -> None:
    """**The window has to be after the disable or it is not evidence about the disable.** A
    window ending at the same instant is the same thing: nothing was watched.

    Delete this and yesterday's observation certifies today's change, which is the most
    natural way to fill this record in from a monitoring dashboard."""
    with pytest.raises(DecommissionError, match="nothing was watched after the disable"):
        ScheduledJob(name="nightly sync", disabled_at=LATER, watched_until=LATER)


def test_a_job_disabled_and_never_watched_is_not_stopped() -> None:
    """M37.1.4.3 asks for jobs disabled **and verified stopped**, and this is the difference
    between the two. **The rule people get wrong by accident.** Disabling a schedule stops
    the next run; it does not stop the run already going, and on several products it does not
    stop a run somebody triggered. A window nobody opened and a window that opened and saw
    nothing are the same empty result and mean opposite things.

    Delete this and `is_stopped` can be written as "was it disabled", which is the flag this
    module exists to argue against."""
    disabled_only = ScheduledJob(name="nightly sync", disabled_at=LATER)

    assert disabled_only.is_stopped() is False


def test_a_job_watched_after_the_disable_with_no_run_is_stopped() -> None:
    """The positive case, and the definition: a window of silence after the disable.

    Delete this and `is_stopped` can be written to return False always, and every
    decommission is permanently outstanding."""
    watched = ScheduledJob(name="nightly sync", disabled_at=LATER, watched_until=LATER_STILL)

    assert watched.is_stopped() is True


def test_a_run_before_the_disable_does_not_keep_a_job_outstanding() -> None:
    """Every job that ever ran has a last run, and it is almost always before the disable.
    Comparing on presence rather than on time would leave every job in the estate outstanding
    for ever, which is a list nobody reads.

    Delete this and the comparison can be written as `last_run_at is not None`."""
    ran_before = ScheduledJob(
        name="nightly sync",
        disabled_at=LATER,
        watched_until=LATER_STILL,
        last_run_at=CUT_OVER,
    )

    assert ran_before.is_stopped() is True
    assert jobs_outstanding((ran_before,)) == ()


def test_the_three_ways_a_job_is_outstanding_are_three_findings() -> None:
    """They send somebody to do three different things: turn it off, go and look, and find out
    what is still triggering it.

    Delete this and all three collapse into "not stopped", which sends whoever reads it to
    disable a job that is already disabled."""
    findings = jobs_outstanding(
        (
            ScheduledJob(name="still on"),
            ScheduledJob(name="unwatched", disabled_at=LATER),
            ScheduledJob(
                name="ran again",
                disabled_at=LATER,
                watched_until=LATER_STILL,
                last_run_at=LATER + timedelta(hours=6),
            ),
        )
    )

    assert findings == (
        "still on: still scheduled",
        f"unwatched: disabled at {LATER} and nobody watched it afterwards",
        f"ran again: disabled at {LATER} and ran again at {LATER + timedelta(hours=6)}",
    )


# ------------------------------------------------------------------- the final backup
def test_a_final_backup_with_no_id_is_refused() -> None:
    """Nothing can be asked for later against a copy with no name.

    Delete this and the blank branch is unreachable."""
    with pytest.raises(DecommissionError, match="has no id"):
        FinalBackup(backup_id="", taken_at=LATER)


def test_when_the_final_backup_may_be_deleted_is_derived_from_the_retention_policy() -> None:
    """**M37.1.4.4 says the final backup is retained per the retention policy**, so the date is
    the policy applied to the backup's own timestamp rather than a date somebody typed.

    Compared against `brain.ops.retention.BACKUP_RETENTION_DAYS` rather than against a number
    written here, so a change to the policy moves this and the module together. That is the
    constant-against-itself rule: a literal in this file would agree with the module for every
    value either could hold.

    Delete this and a final backup is kept for a round number that matches no policy
    anywhere."""
    backup = FinalBackup(backup_id="b1", taken_at=LATER)

    assert backup.may_delete_after() == LATER + timedelta(days=BACKUP_RETENTION_DAYS)
    assert backup.may_delete_after(retention_days=1) == LATER + timedelta(days=1)


# ----------------------------------------------------------------------- the whole record
def test_a_decommission_nobody_finished_names_every_step_still_outstanding() -> None:
    """The system, then the credentials, which are the only part of this on somebody else's
    service, then the jobs, then the backup.

    Delete this and the steps are reported one at a time, and whoever is working the list
    stops when the screen goes green rather than when the system is off."""
    record = Decommission(
        cut_over_at=CUT_OVER,
        revocations=(Revocation(connector="drive"),),
        jobs=(ScheduledJob(name="nightly sync"),),
    )

    assert decommission_gaps(record) == (
        "the old system still accepts writes",
        "the old system has not been archived",
        "drive: nobody has asked for this grant to be withdrawn",
        "nightly sync: still scheduled",
        "no final backup was taken",
    )


def test_a_final_backup_nobody_verified_is_a_file_rather_than_a_copy() -> None:
    """An unverified backup is the one everybody assumes is fine, and it is the assumption
    this repository already refuses in `brain.ops.recovery` for the live system. The last copy
    of a system that is about to be switched off is the worst place to relax it.

    Delete this and a decommission reports complete with a backup nobody has read."""
    record = a_record(final_backup=FinalBackup(backup_id="b1", taken_at=LATER))

    assert decommission_gaps(record) == (
        "the final backup b1 has never been verified, so what is retained is a file rather "
        "than a copy anybody has read",
    )


def test_a_finished_decommission_has_no_findings() -> None:
    """The positive case for the whole module.

    Delete this and every check above can be strengthened until no system is ever switched
    off."""
    record = a_record(
        revocations=(Revocation(connector="drive", requested_at=LATER, verified_at=LATER_STILL),),
        jobs=(ScheduledJob(name="nightly sync", disabled_at=LATER, watched_until=LATER_STILL),),
    )

    assert decommission_gaps(record) == ()
