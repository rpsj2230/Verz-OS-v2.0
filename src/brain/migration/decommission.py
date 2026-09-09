"""Turning the old system off, in an order that cannot be done backwards.

Four things happen to a system that has been replaced, and each of them is routinely reported
as done when it is not. This module is the register that refuses those reports.

**The order is the rule and it is enforced rather than described.** Read-only comes after the
cutover, because a system made read-only during a comparison period stops answering the
questions the period exists to ask. Archived comes after read-only, because a system archived
while somebody can still write to it is a system whose archive is already out of date. Written
as a runbook these are three sentences somebody follows in whatever order the week allows, so
they are timestamps here and `Decommission` refuses them out of order.

**A revocation that was requested is not a revocation.** Every connector the old system held
is a live grant on somebody else's service, and asking for it to be withdrawn and confirming
it was withdrawn are different facts arriving at different times, sometimes never. The two
outstanding states reach different people: a grant nobody has asked about needs whoever holds
the account, and a grant asked about and never confirmed needs whoever asked. They are
reported separately for that reason. See
`A_REVOCATION_NOBODY_CONFIRMED_IS_A_CREDENTIAL_THAT_STILL_WORKS`.

**Verified stopped is a window of silence, not a flag**, and this is the one people get wrong
by accident. Disabling a schedule stops the next run; it does not stop the run already going,
and on several products it does not stop a run that a person triggered. So a job is verified
stopped when something watched it for a while after the disable and saw nothing, and a job
that was disabled and never watched afterwards is **not** verified: an observation window that
was never opened and one that opened and saw nothing are the same empty result and mean
opposite things, which is the distinction `brain.migration.inventory` is built around. See
`A_DISABLED_JOB_AND_A_STOPPED_JOB_ARE_DIFFERENT_FACTS`.

**A completed cutover is refused while any act with a security consequence is unrecorded**,
and that is the newest of the refusals here. Five leaves of the plan are things a person does
rather than code anybody could write, and their absence is not untidiness: an OAuth grant
nobody withdrew is how an outgoing vendor keeps reading a client's mail after the account is
believed closed, and a date nobody recorded cannot be reconstructed afterwards. They are named
in `brain.migration.checklist.CUTOVER_GATED_ACTS` and `CompletedCutover` cannot be built while
one of them is missing. That is what makes the delivery checklist something other than a list:
it gates the day rather than the build. See `AN_ACT_NOBODY_RECORDED_IS_AN_ACT_NOBODY_DID`.

They are refused here and not folded into `decommission_gaps`, which is the tidier-looking
design and answers a different question. That function reports what is still true of the old
system; two of the gated acts are about the client's own tenant and the client's own backup and
are not facts about the old system at all. Folding them in would also make the default empty
tuple of acts mean "nothing was required", which is the permissive reading of an absence and
the one this repository refuses everywhere else.

**The final backup's retention is derived and never typed.** M37.1.4.4 says the final backup is
retained per the retention policy, and the policy is `brain.ops.retention.BACKUP_RETENTION_DAYS`.
A date typed into a decommission record is a date somebody worked out on the day, which is how
a final backup ends up retained for a round number that matches nothing. `may_delete_after`
adds the policy to the backup's own timestamp, so a change to the policy moves every
outstanding decommission with it.

What was rejected. A single `done` flag per step, which is what a checklist gives you and what
every one of the four failures above looks like from the outside. Each of these has a moment
attached because the questions that get asked afterwards are about order and about gaps, and a
flag answers neither.

Nothing here reaches the old system. Whether a credential still works is a question for a
connector, and this holds what somebody observed, so the case that matters, a report of
verification that is not one, can be built in a test.

Task ids: M37.1.4.1, M37.1.4.2, M37.1.4.3, M37.1.4.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.migration.checklist import CUTOVER_GATED_ACTS
from brain.migration.inventory import MigrationError
from brain.ops.retention import BACKUP_RETENTION_DAYS


class DecommissionError(MigrationError):
    """Raised when a decommission record would report something that did not happen."""


# ------------------------------------------------------------------ written-down reasons
#: Why asking for a grant to be withdrawn is not the same as it being withdrawn.
A_REVOCATION_NOBODY_CONFIRMED_IS_A_CREDENTIAL_THAT_STILL_WORKS: Final = (
    "Every connector the old system held is a live grant on somebody else's service, and "
    "cancelling a subscription does not withdraw one. Asking and confirming are different "
    "facts that arrive at different times and sometimes never, so a request with no "
    "confirmation is counted as outstanding rather than as done. It is reported separately "
    "from a grant nobody has asked about, because the two reach different people: one needs "
    "whoever holds the account and the other needs whoever asked."
)

#: Why a disabled schedule is not a stopped one.
A_DISABLED_JOB_AND_A_STOPPED_JOB_ARE_DIFFERENT_FACTS: Final = (
    "Disabling a schedule stops the next run. It does not stop the run already going, and on "
    "several products it does not stop a run a person triggered. So stopped is a window of "
    "silence after the disable rather than a flag, and a job disabled and never watched "
    "afterwards is not verified: an observation window nobody opened and one that opened and "
    "saw nothing are the same empty result, and they mean opposite things."
)

#: Why the acts with a security consequence stop a cutover being reported complete.
AN_ACT_NOBODY_RECORDED_IS_AN_ACT_NOBODY_DID: Final = (
    "Five leaves of the plan are things a person does on the week of a migration, and each of "
    "them leaves a way in if it is skipped: a grant nobody withdrew, an application still "
    "installed in the tenant, a bot still sitting in a group, a date nobody wrote down, a "
    "backup nobody has read back. None of them can be verified from here, so what is recorded "
    "is that somebody did it and who says so. An unrecorded act and an act nobody did are the "
    "same absence from this side, and the permissive reading of that absence is how every one "
    "of them gets missed, so the cutover is refused rather than reported with a note."
)

#: Why archiving is not the first thing that happens.
AN_ARCHIVE_TAKEN_WHILE_SOMEBODY_CAN_STILL_WRITE_IS_ALREADY_OUT_OF_DATE: Final = (
    "The old system is made read-only first and archived afterwards, and the order is the "
    "whole of what makes the archive worth keeping. Reversed, the archive is a copy of a "
    "system that carried on changing, and nothing about it says so. Read-only itself waits "
    "for the cutover, because a system made read-only during a comparison period stops "
    "answering the questions the period exists to ask."
)


# -------------------------------------------------------------- the credentials (M37.1.4.2)
@dataclass(frozen=True)
class Revocation:
    """One connector the old system held, and how far its withdrawal actually got.

    `verified_at` is what makes it a revocation. `requested_at` is what makes it a request.
    """

    connector: str
    requested_at: datetime | None = None
    verified_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.connector.strip():
            msg = "a revocation names no connector"
            raise DecommissionError(msg)
        if self.verified_at is not None and self.requested_at is None:
            msg = (
                f"{self.connector!r} was verified revoked and nobody asked for it, which is a "
                "record of a confirmation that has nothing to confirm"
            )
            raise DecommissionError(msg)
        if (
            self.verified_at is not None
            and self.requested_at is not None
            and self.verified_at < self.requested_at
        ):
            msg = (
                f"{self.connector!r} was verified revoked at {self.verified_at}, before it "
                "was asked"
            )
            raise DecommissionError(msg)


def credentials_outstanding(revocations: Sequence[Revocation]) -> tuple[str, ...]:
    """Grants still live, never asked about first, then asked about and never confirmed.

    Two lists in one, ordered so the reader meets the ones nobody has touched before the ones
    somebody is already chasing. See
    `A_REVOCATION_NOBODY_CONFIRMED_IS_A_CREDENTIAL_THAT_STILL_WORKS`.
    """
    findings = [
        f"{one.connector}: nobody has asked for this grant to be withdrawn"
        for one in revocations
        if one.requested_at is None
    ]
    findings.extend(
        f"{one.connector}: withdrawal asked for at {one.requested_at} and never confirmed"
        for one in revocations
        if one.requested_at is not None and one.verified_at is None
    )
    return tuple(findings)


# ---------------------------------------------------------- the scheduled jobs (M37.1.4.3)
@dataclass(frozen=True)
class ScheduledJob:
    """One job on the old system, when it was disabled, and what was seen afterwards.

    `watched_until` is how far the observation window extends and `last_run_at` is the most
    recent run seen. Both, because an unopened window and an empty one are the same absence.
    """

    name: str
    disabled_at: datetime | None = None
    watched_until: datetime | None = None
    last_run_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a scheduled job has no name"
            raise DecommissionError(msg)
        if self.watched_until is not None and self.disabled_at is None:
            msg = f"{self.name!r} was watched for runs and was never disabled"
            raise DecommissionError(msg)
        if (
            self.watched_until is not None
            and self.disabled_at is not None
            and self.watched_until <= self.disabled_at
        ):
            msg = (
                f"{self.name!r} was watched until {self.watched_until} and disabled at "
                f"{self.disabled_at}, so nothing was watched after the disable"
            )
            raise DecommissionError(msg)

    def is_stopped(self) -> bool:
        """Whether somebody watched this after disabling it and saw nothing run."""
        if self.disabled_at is None or self.watched_until is None:
            return False
        return self.last_run_at is None or self.last_run_at <= self.disabled_at


def jobs_outstanding(jobs: Sequence[ScheduledJob]) -> tuple[str, ...]:
    """Jobs not disabled, then disabled and unwatched, then watched and still running.

    Three findings and not one, because they send somebody to do three different things: turn
    it off, go and look, and find out what is still triggering it. See
    `A_DISABLED_JOB_AND_A_STOPPED_JOB_ARE_DIFFERENT_FACTS`.
    """
    findings = [f"{one.name}: still scheduled" for one in jobs if one.disabled_at is None]
    findings.extend(
        f"{one.name}: disabled at {one.disabled_at} and nobody watched it afterwards"
        for one in jobs
        if one.disabled_at is not None and one.watched_until is None
    )
    findings.extend(
        f"{one.name}: disabled at {one.disabled_at} and ran again at {one.last_run_at}"
        for one in jobs
        if one.disabled_at is not None
        and one.watched_until is not None
        and one.last_run_at is not None
        and one.last_run_at > one.disabled_at
    )
    return tuple(findings)


# --------------------------------------------------------------- the final backup (M37.1.4.4)
@dataclass(frozen=True)
class FinalBackup:
    """The last copy taken of the old system before it was switched off."""

    backup_id: str
    taken_at: datetime
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.backup_id.strip():
            msg = "the final backup has no id, so nothing can be asked for it later"
            raise DecommissionError(msg)

    def may_delete_after(self, retention_days: int = BACKUP_RETENTION_DAYS) -> datetime:
        """When the retention policy stops requiring this copy.

        Derived from the policy rather than typed into the record, so a change to
        `brain.ops.retention.BACKUP_RETENTION_DAYS` moves every outstanding decommission with
        it. A typed date is one somebody worked out on the day, which is how a final backup
        ends up kept for a round number that matches no policy anywhere.
        """
        return self.taken_at + timedelta(days=retention_days)


# ------------------------------------------------------ the acts a person does on the week
@dataclass(frozen=True)
class ActRecord:
    """One item off the delivery checklist, and who says it happened.

    `recorded_by` is not administrative. Nothing here can reach the outgoing system, so the
    whole content of this record is somebody's word that they did it, and a word with no name
    on it is a tick. It is the same distinction `ScheduledJob` draws between a job that was
    disabled and a job somebody watched.
    """

    leaf: str
    performed_at: datetime
    recorded_by: str

    def __post_init__(self) -> None:
        if not self.leaf.strip():
            msg = "an act record names no task, so nothing can be found on the checklist"
            raise DecommissionError(msg)
        if not self.recorded_by.strip():
            msg = (
                f"the act recorded against {self.leaf!r} says who did it nowhere, and nothing "
                "here can check it, so an unattributed record is a tick"
            )
            raise DecommissionError(msg)


# ------------------------------------------------------------- the order of it (M37.1.4.1)
@dataclass(frozen=True)
class Decommission:
    """The whole record, with the three moments in the order they have to happen in."""

    cut_over_at: datetime
    read_only_at: datetime | None = None
    archived_at: datetime | None = None
    revocations: tuple[Revocation, ...] = ()
    jobs: tuple[ScheduledJob, ...] = ()
    final_backup: FinalBackup | None = None
    #: What somebody did on the week, off `docs/delivery-checklist.md`. Empty by default and
    #: empty is not "none were required": the five that gate are required whatever this holds.
    acts: tuple[ActRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.read_only_at is not None and self.read_only_at < self.cut_over_at:
            msg = (
                f"the old system was made read-only at {self.read_only_at}, before the cutover "
                f"at {self.cut_over_at}. "
                f"{AN_ARCHIVE_TAKEN_WHILE_SOMEBODY_CAN_STILL_WRITE_IS_ALREADY_OUT_OF_DATE}"
            )
            raise DecommissionError(msg)
        if self.archived_at is not None and self.read_only_at is None:
            msg = (
                f"the old system was archived at {self.archived_at} and never made read-only. "
                f"{AN_ARCHIVE_TAKEN_WHILE_SOMEBODY_CAN_STILL_WRITE_IS_ALREADY_OUT_OF_DATE}"
            )
            raise DecommissionError(msg)
        if (
            self.archived_at is not None
            and self.read_only_at is not None
            and self.archived_at < self.read_only_at
        ):
            msg = (
                f"the old system was archived at {self.archived_at} and made read-only at "
                f"{self.read_only_at}, which is the wrong way round. "
                f"{AN_ARCHIVE_TAKEN_WHILE_SOMEBODY_CAN_STILL_WRITE_IS_ALREADY_OUT_OF_DATE}"
            )
            raise DecommissionError(msg)


# --------------------------------------------------------- what a cutover may be reported as
def security_acts_outstanding(record: Decommission) -> tuple[str, ...]:
    """The acts with a security consequence that nobody has recorded doing.

    Ordered by task id rather than by the order somebody happened to record them, so two
    reports of the same cutover read the same way and a diff between them says something. See
    `AN_ACT_NOBODY_RECORDED_IS_AN_ACT_NOBODY_DID`.
    """
    recorded = {one.leaf for one in record.acts}
    return tuple(
        f"{leaf}: {what}"
        for leaf, what in sorted(CUTOVER_GATED_ACTS.items())
        if leaf not in recorded
    )


def may_report_complete(record: Decommission) -> bool:
    """Whether this cutover can be reported complete, asked without raising."""
    return not security_acts_outstanding(record)


@dataclass(frozen=True)
class CompletedCutover:
    """A cutover reported complete, which cannot be built while a gated act is unrecorded.

    A dataclass rather than a function returning a boolean, and the reason is the same one the
    three moments above are timestamps rather than flags: the refusal has to sit where the
    claim is made. Somewhere there is a screen, a report or a handover pack that says the
    cutover is done, and whatever writes it constructs this. There is no arrangement of these
    fields that says so while an act is outstanding, in the way
    `brain.migration.skills.arriving` has nowhere to put another platform's approval.

    It carries the whole record rather than a summary, because the question asked afterwards
    is never "was it complete" on its own, it is "what did complete mean on that day".
    """

    record: Decommission
    reported_by: str

    def __post_init__(self) -> None:
        if not self.reported_by.strip():
            msg = "a completed cutover was reported by nobody"
            raise DecommissionError(msg)
        outstanding = security_acts_outstanding(self.record)
        if outstanding:
            msg = (
                f"the cutover at {self.record.cut_over_at} cannot be reported complete: "
                f"{len(outstanding)} act(s) with a security consequence are unrecorded. "
                f"{'; '.join(outstanding)}. {AN_ACT_NOBODY_RECORDED_IS_AN_ACT_NOBODY_DID}"
            )
            raise DecommissionError(msg)


def decommission_gaps(record: Decommission) -> tuple[str, ...]:
    """Everything still true of a system somebody believes is switched off.

    The order is what somebody reads down: the system itself, then the credentials, which are
    the only part of this that is somebody else's service, then the jobs, then the backup.
    """
    findings: list[str] = []
    if record.read_only_at is None:
        findings.append("the old system still accepts writes")
    if record.archived_at is None:
        findings.append("the old system has not been archived")
    findings.extend(credentials_outstanding(record.revocations))
    findings.extend(jobs_outstanding(record.jobs))
    if record.final_backup is None:
        findings.append("no final backup was taken")
    elif not record.final_backup.verified:
        findings.append(
            f"the final backup {record.final_backup.backup_id} has never been verified, so "
            "what is retained is a file rather than a copy anybody has read"
        )
    return tuple(findings)
