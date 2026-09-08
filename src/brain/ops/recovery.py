"""What a backup is, and the single thing that turns one into a recovery.

Everything around a backup already existed in this repository and nothing wrote to it.
`brain.ops.storage` declares a `backups` bucket, `ops/seaweedfs/provision.sh` gives it a
35 day lifecycle, `brain.ops.retention.BACKUP_RETENTION_DAYS` reads that rule, and
`brain.ops.erasure.backup_horizon` does arithmetic on the number so a deletion certificate
can say what it has not reached. Four modules describing the lifecycle of an empty shelf.
This module is the vocabulary the thing on that shelf needs before anybody may call it a
backup, and the reason it is a domain layer with no runner attached is at the bottom.

**A backup nobody has restored is a file.** That is the whole of this module and every
refusal below is a consequence of it. A dump that was written, uploaded, retained, versioned
and never read back is indistinguishable, from outside, from a dump that is truncated,
encrypted with a lost key, or taken from a replica that had stopped replicating. The
distinguishing act is reading it back and asking it questions, and until somebody has, the
honest word for the artefact is file. See `A_BACKUP_NOBODY_HAS_RESTORED_IS_A_FILE`.

**So an attempted restore and a verified restore are two different objects and neither is
convertible into the other by optimism.** A `Drill` is what happened: a backup was read into
a scratch target and some checks ran. A `Verification` is what it proved, and
`verification_of` is the only way to obtain one. There is no constructor path from a drill
that failed to a verification that says it succeeded, and no field on a verification a
caller can set to say otherwise. See `AN_ATTEMPTED_RESTORE_IS_NOT_A_VERIFIED_ONE`.

**A drill that did not verify has no recovery time, and that refusal is enforced rather than
documented.** The natural implementation records the elapsed time of every drill, and the
number an operator then reads is "we were back in forty minutes" from a run that restored
in forty minutes and failed its permission canary. That drill recovered nothing in forty
minutes; it produced a database that answers every question for everybody. `Verification`
refuses to hold an `rto_seconds` unless `verified` is true, and refuses to omit one when it
is. See `A_DRILL_THAT_DID_NOT_VERIFY_HAS_NO_RECOVERY_TIME`.

**The permission canary is a required check rather than a thorough one.** A restore brings
back rows. Whether it brings back the row-level security policies, the role grants and the
`brain_fastlane` restriction that decide who may read those rows is a separate question with
a separate answer, and the failure is silent in the direction that matters: a restored copy
missing its policies answers everything, to everybody, correctly. A smoke query cannot see
that, because a smoke query asks whether the data came back and the data did. See
`A_RESTORE_CAN_BRING_BACK_EVERY_ROW_AND_NONE_OF_THE_POLICIES`.

`REQUIRED_CHECKS` is therefore every member of `Check` and there are no optional ones. The
third, `SCHEMA_COMPLETE`, is not named by the leaf and is here because a smoke query written
as a trivial select passes against an empty database, so the two checks the leaf does name
are both satisfiable by a restore that restored nothing.

**A drill restores into a scratch target and `Drill` will not be constructed otherwise.**
The field exists for the same reason `brain.ops.storage.Bucket.public_read` does: nothing
sets it wrong, and it is present so that a runner pointed at the live database is refused by
a value class before it reaches a connection. A weekly automated restore that can be
misconfigured into the production database is a scheduled outage.

**An RPO is a promise about the slowest copy that has to come back with the rest.** The
database is archived continuously and the object store is snapshotted on an interval, so a
profile stating one recovery point objective is stating the object store's, whatever the
database can do. `backup_policy_gaps` compares the objectives against `SCHEDULE` rather than
leaving the promise to be read off the fastest component. See
`AN_RPO_IS_A_PROMISE_ABOUT_THE_SLOWEST_COPY`.

**M30.3.5's retention ladder cannot be adopted today and this module says so rather than
implementing it.** Thirty daily, twelve weekly and twelve monthly copies puts the oldest
retained backup 372 days old. `BACKUP_RETENTION_DAYS` is 35, and every erasure certificate
this system has a shape for tells a person their data is beyond backup reach 35 days after
the deletion completed. Adopting the ladder without moving that number makes every one of
those certificates wrong by 337 days, silently, in the direction that matters to a
regulator. `RETENTION_LADDER` is declared so the arithmetic is checkable and
`backup_policy_gaps` reports the conflict; nothing prunes to it. See
`THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES`.

Rejected: a `RecoveryPanel` record with a field per thing the console screen wants.
`brain.ops.admission` removed exactly that shape for exactly this reason and recorded why:
nothing constructs one, so its fields would be chosen by whoever wrote this file rather than
by the screen that has to render them. What a panel needs is two questions, `latest` and
`last_verified_restore`, and both are answerable without a record wrapping them. M27.6.2 stays
unclaimed for a different reason than it did yesterday: not that nothing here can say what a
verified restore is, but that nothing produces one to show.

Rejected: recording the age of the newest object in the `backups` bucket as a backup
timestamp. It is the number that is available and it answers a different question, which is
whether anything was uploaded, not whether anything can be read back.

Scope: domain logic. Nothing here takes a dump, opens a connection, runs a container, reads
a clock or writes a schedule. Every clock is a parameter and every observation is handed in,
for the reason `brain.ops.limits` gives about policy that owns a client: the case that is
always wrong is the one you cannot reach through the module that owns the data.

Task ids: M30.3.3, M30.3.4, M30.3.6, M30.3.7, M30.3.8, M30.3.10, M30.3.11
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.ops.reliability import RECOVERY_OBJECTIVES, RecoveryObjective, recovery_objective
from brain.ops.retention import BACKUP_RETENTION_DAYS

# ----------------------------------------------------------------- written-down reasons
#: The sentence this module exists to make structural.
A_BACKUP_NOBODY_HAS_RESTORED_IS_A_FILE: Final = (
    "A dump that was written, uploaded, retained and never read back is indistinguishable "
    "from outside from one that is truncated, encrypted with a key nobody has, or taken "
    "from a replica that had silently stopped replicating. Every one of those looks the "
    "same in a bucket listing: a recent object of a plausible size. The act that "
    "distinguishes them is reading it back and asking it questions, so until somebody has, "
    "the honest word for the artefact is file, and a console field reading last backup is "
    "reporting the size of a file."
)

#: Why a drill and a verification are two objects rather than one with a flag.
AN_ATTEMPTED_RESTORE_IS_NOT_A_VERIFIED_ONE: Final = (
    "A restore that ran is a statement about this system: a process started, read some "
    "bytes and exited. A restore that verified is a statement about the copy it produced: "
    "it holds the schema, it answers a known question with the known answer, and it still "
    "refuses what it should refuse. The first is evidence for the second and is not the "
    "second, and the whole reason the distinction needs a type rather than a convention is "
    "that the interesting failure is a restore that completes and produces something wrong."
)

#: Why an unverified drill carries no recovery time.
A_DRILL_THAT_DID_NOT_VERIFY_HAS_NO_RECOVERY_TIME: Final = (
    "The obvious implementation times every drill and stores the elapsed seconds. An "
    "operator then reads forty minutes off a run that restored in forty minutes and failed "
    "its permission canary, and plans an incident around a number that describes producing "
    "a database which answers every question for everybody. A recovery time is time to "
    "recovery. A drill that did not recover anything has not measured one, and reporting "
    "its duration under that heading is worse than reporting nothing, because nothing "
    "prompts somebody to ask."
)

#: Why the permission canary is required rather than thorough.
A_RESTORE_CAN_BRING_BACK_EVERY_ROW_AND_NONE_OF_THE_POLICIES: Final = (
    "Restoring rows and restoring the rules about who may read them are two operations, "
    "and the second is the one that fails quietly. A copy restored without its row-level "
    "security policies, its role grants and the brain_fastlane restriction answers "
    "everything, to everybody, with correct data, and passes any smoke query anybody would "
    "write. So the check that a restricted field is still refused is not extra assurance "
    "on top of a working restore, it is the only check that can see this failure at all."
)

#: Why a scratch target is a refusal at construction.
A_DRILL_AGAINST_THE_LIVE_SYSTEM_IS_A_SCHEDULED_OUTAGE: Final = (
    "The value of an automated weekly restore is that nobody has to remember to run it. "
    "The cost of one pointed at the wrong target is that nobody has to remember to destroy "
    "production either. The field is refused here rather than checked in a runner because "
    "a runner is where the misconfiguration lives, and a value class that cannot hold the "
    "mistake is the only guard that survives the runner being rewritten."
)

#: Why one recovery point objective per profile is a claim about the slowest copy.
AN_RPO_IS_A_PROMISE_ABOUT_THE_SLOWEST_COPY: Final = (
    "Continuous write-ahead archiving puts the database's exposure a minute behind, and a "
    "snapshot of the object store puts its exposure at the snapshot interval. A client "
    "reading one recovery point objective reads the smaller number and hears it about "
    "their whole system, which is true of the database and false of every uploaded "
    "document. So the objective is compared against the slowest thing in SCHEDULE rather "
    "than against the component whose figure sounds best."
)

#: Why the ladder M30.3.5 asks for is declared and not adopted.
THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES: Final = (
    "Thirty daily, twelve weekly and twelve monthly copies keeps a backup that is up to "
    "372 days old. brain.ops.erasure.backup_horizon adds BACKUP_RETENTION_DAYS to a "
    "completed deletion and a certificate states that date as the moment the data is "
    "beyond backup reach. Adopting the ladder without moving that number does not make a "
    "certificate late, it makes it false, by 337 days, on a document written for somebody "
    "who asked to be forgotten. Which of the two numbers moves is a decision with a legal "
    "side and a storage bill, and it is not one this module may take by pruning."
)

#: Why every figure below is a default rather than a requirement.
THE_NEXT_COMPANY_KEEPS_ITS_OWN_COPIES_FOR_ITS_OWN_REASONS: Final = (
    "Every interval and every count here is a starting position for an install nobody has "
    "configured yet. A firm that has to reproduce a ledger for seven years and a firm "
    "whose oldest interesting record is last quarter need different answers, and neither "
    "is served by a constant in a module. So the checks take their policy as a parameter "
    "and default to these, which means a client's own figures go through the same "
    "arithmetic rather than round the outside of it."
)


class RecoveryError(Exception):
    """Raised when something is described as a backup, a drill or a recovery time it is not."""


# --------------------------------------------------------------------- the vocabulary
class Coverage(enum.StrEnum):
    """What a copy is a copy of.

    Three rather than one, because they are protected by different tools with different
    intervals and a single answer to "when was the last backup" hides the slowest of them.
    """

    #: The application's PostgreSQL. Continuously archived, so its exposure is minutes.
    DATABASE = "database"
    #: The object store's buckets: originals, exports, recordings.
    OBJECT_STORE = "object_store"
    #: What the install is, as opposed to what it holds. Compose, realm, policies, keys.
    CONFIGURATION = "configuration"


class Method(enum.StrEnum):
    """How a copy was produced. Named because the method decides the exposure.

    `CONTINUOUS_WAL` is the only member whose copy can restore to a moment after the copy
    finished, and that is the property the recovery point objective rests on: without it,
    the best case after a failure is the last full or incremental run.
    """

    CONTINUOUS_WAL = "continuous_wal"
    INCREMENTAL = "incremental"
    FULL = "full"
    SNAPSHOT = "snapshot"


class KeyHolder(enum.StrEnum):
    """Who can decrypt the copy.

    `NOBODY` is unencrypted rather than lost. It reads oddly and it is the honest name:
    a copy anybody with the bytes can read is a copy whose key everybody holds.
    """

    CLIENT = "client"
    PLATFORM = "platform"
    NOBODY = "nobody"


class Check(enum.StrEnum):
    """What a drill asks the restored copy. Every member is required; see `REQUIRED_CHECKS`."""

    #: Every schema, table and policy the code expects is present in the restored copy.
    SCHEMA_COMPLETE = "schema_complete"
    #: A known question returns the known answer from the restored copy.
    SMOKE_QUERY = "smoke_query"
    #: A restricted field is still refused to a principal who may not read it. See
    #: `A_RESTORE_CAN_BRING_BACK_EVERY_ROW_AND_NONE_OF_THE_POLICIES`.
    PERMISSION_CANARY = "permission_canary"


class Severity(enum.IntEnum):
    """How loud an alert is, as a comparison rather than as a convention.

    An `IntEnum` so that "louder" is `>` and a test can assert the ordering. Two members
    because there are two things worth waking somebody for, and a third level invented for
    tidiness is a level nobody tunes.
    """

    #: There is no copy of the last stretch of work. Includes never having taken one:
    #: an absent backup and an aged backup are the same fact with the same remedy, and
    #: splitting them gives an operator two thresholds where there is one problem.
    BACKUP_AGED = 1
    #: A drill ran and did not verify, which means every copy held is of unknown
    #: readability rather than one of them being bad.
    VERIFICATION_FAILED = 2


# --------------------------------------------------------------- where a copy is kept
@dataclass(frozen=True)
class Destination:
    """One place copies are written, and the two properties that decide whether it helps.

    Both are declared rather than inferred. Whether a bucket is on the same host as the
    database is not visible from an endpoint URL once the endpoint is a name, and who holds
    the encryption key is not visible from anywhere at all.
    """

    name: str
    covers: frozenset[Coverage]
    #: False when the copy lives on the machine it is a copy of.
    off_host: bool
    key_held_by: KeyHolder
    because: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a destination with no name cannot be found by whoever needs it at 3am"
            raise RecoveryError(msg)
        if not self.covers:
            msg = f"destination {self.name!r} is a copy of nothing"
            raise RecoveryError(msg)
        if not self.because.strip():
            msg = (
                f"destination {self.name!r} states no reason, and an unexplained backup "
                "target is the one that gets pointed somewhere cheaper"
            )
            raise RecoveryError(msg)


def destination_gaps(destinations: Sequence[Destination]) -> tuple[str, ...]:
    """Every way a set of destinations fails to protect what it claims to (M30.3.3, M30.3.4).

    Takes the destinations rather than reading a declared constant, because there is no
    declared constant to read: where a client's copies go is configuration set during setup,
    and a list of endpoints in this repository would be one company's answer compiled into
    the product. It is also what makes the refusals reachable: a check that can only run
    against a healthy declaration cannot be shown to fail.

    Returns all of them rather than the first, for the reason
    `brain.ops.storage.lifecycle_gaps` takes the same shape: the reader is somebody
    comparing a configuration against the rules, and the useful output is the whole list.
    """
    findings: list[str] = []
    for one in destinations:
        if not one.off_host:
            findings.append(
                f"{one.name}: on the same host as what it copies, so the failure that "
                "destroys the original destroys the copy in the same second"
            )
        if one.key_held_by is KeyHolder.NOBODY:
            findings.append(
                f"{one.name}: unencrypted, so the copy carries every field the permission "
                "layer protects with none of the permission layer attached to it"
            )
        if one.key_held_by is KeyHolder.PLATFORM:
            findings.append(
                f"{one.name}: encrypted with a key this platform holds rather than the "
                "client, which makes their records ours to lose and ours to be compelled for"
            )
    covered = {kind for one in destinations for kind in one.covers}
    findings.extend(
        f"{kind.value}: nothing copies it anywhere, so the answer to losing it is that it is lost"
        for kind in Coverage
        if kind not in covered
    )
    return tuple(findings)


# ------------------------------------------------------------------------ a copy
@dataclass(frozen=True)
class Backup:
    """One copy that was taken, as the thing that took it can honestly describe it.

    `recoverable_to` is the field that matters and it is not `finished_at`. For a full or
    an incremental copy the two are the same. For continuous archiving the copy can restore
    to a moment after the run that produced it, because segments keep arriving, and the
    exposure a recovery point objective is measured against is that later moment. Recording
    only `finished_at` would report an exposure of a week on a database that is a minute
    behind.
    """

    backup_id: str
    coverage: Coverage
    method: Method
    destination: str
    started_at: datetime
    finished_at: datetime
    #: The latest moment this copy can restore the system to.
    recoverable_to: datetime
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.backup_id.strip():
            msg = "a backup with no id cannot be named by a restore, an alert or a drill"
            raise RecoveryError(msg)
        for name in ("started_at", "finished_at", "recoverable_to"):
            when: datetime = getattr(self, name)
            if when.tzinfo is None:
                msg = (
                    f"{name} on backup {self.backup_id!r} is naive, so the exposure computed "
                    "from it is wrong by whatever this machine's offset happens to be"
                )
                raise RecoveryError(msg)
        if self.finished_at < self.started_at:
            msg = f"backup {self.backup_id!r} finished before it started"
            raise RecoveryError(msg)
        if self.size_bytes < 1:
            msg = (
                f"backup {self.backup_id!r} is {self.size_bytes} bytes. A dump command that "
                "exits zero having written nothing is the commonest silent backup failure "
                "there is, and it is invisible in every listing that shows a timestamp"
            )
            raise RecoveryError(msg)
        if self.recoverable_to < self.started_at:
            msg = (
                f"backup {self.backup_id!r} claims to restore to a moment before it began "
                "reading, which is a copy of something older than itself"
            )
            raise RecoveryError(msg)
        if self.method is not Method.CONTINUOUS_WAL and self.recoverable_to > self.finished_at:
            msg = (
                f"backup {self.backup_id!r} is a {self.method.value} copy claiming to "
                "restore past the moment it finished; only continuous archiving can do that"
            )
            raise RecoveryError(msg)


def latest(backups: Sequence[Backup], coverage: Coverage) -> Backup | None:
    """The copy of this coverage that reaches furthest forward, or `None` for no copy at all.

    Ordered by `recoverable_to` rather than by `finished_at`, which is the same distinction
    the field exists for: last week's full backup plus this minute's archived segments
    reaches further than yesterday's incremental, and a panel showing the newest run would
    show the wrong one.

    `None` rather than raising, because no copy at all is the state this repository is
    actually in and it is an answer a caller has to render rather than an error.
    """
    of_kind = [one for one in backups if one.coverage is coverage]
    if not of_kind:
        return None
    return max(of_kind, key=lambda one: (one.recoverable_to, one.backup_id))


def exposure_seconds(
    backups: Sequence[Backup], coverage: Coverage, *, now: datetime
) -> float | None:
    """How much work is not anywhere else, in seconds. `None` when nothing covers this.

    This is the measured recovery point, against which a profile's objective is a promise.

    A copy that reaches into the future is refused rather than clamped to zero. The cause is
    a clock disagreement between whatever wrote the copy and this process, and clamping
    reports a healthier exposure than the truth, which is the one direction an operator must
    never be lied to in.
    """
    if now.tzinfo is None:
        msg = "a naive now measures exposure at this machine's offset rather than in UTC"
        raise RecoveryError(msg)
    newest = latest(backups, coverage)
    if newest is None:
        return None
    if newest.recoverable_to > now:
        msg = (
            f"backup {newest.backup_id!r} restores to a moment that has not happened, so a "
            "clock somewhere disagrees and the exposure computed here would read smaller "
            "than the truth"
        )
        raise RecoveryError(msg)
    return (now - newest.recoverable_to).total_seconds()


# ------------------------------------------------------------------------ the drill
@dataclass(frozen=True)
class CheckRun:
    """One question asked of the restored copy, and what came back in words.

    `detail` is prose about what was asked and what happened, never a value read out of the
    restored copy. `brain.ops.canaries.A_FINDING_REPEATS_THE_LEAK_IF_IT_CARRIES_THE_VALUE`
    is the rule and it applies with more force here: a drill report goes into a ticket and
    an alert, and a canary token quoted in one is the leak happening again through the
    document about the leak.
    """

    check: Check
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            msg = (
                f"check {self.check.value} says nothing about what it asked, so a failure "
                "arrives as a red light with no bulb behind it"
            )
            raise RecoveryError(msg)


@dataclass(frozen=True)
class Drill:
    """One restore that was attempted. Not a claim that anything was recovered (M30.3.6).

    `finished_at` is when the last check completed rather than when the bytes finished
    loading, because the recovery time an operator plans around is time until the system can
    be used, and a copy nobody has questioned yet cannot be used.
    """

    backup_id: str
    started_at: datetime
    finished_at: datetime
    #: Whether the copy was restored into a throwaway target. See
    #: `A_DRILL_AGAINST_THE_LIVE_SYSTEM_IS_A_SCHEDULED_OUTAGE`. Nothing sets it false; the
    #: field exists so that a runner which would have is refused before it opens anything.
    into_scratch: bool
    checks: tuple[CheckRun, ...]

    def __post_init__(self) -> None:
        if not self.backup_id.strip():
            msg = "a drill that cannot say which copy it read has verified nothing in particular"
            raise RecoveryError(msg)
        for name in ("started_at", "finished_at"):
            when: datetime = getattr(self, name)
            if when.tzinfo is None:
                msg = f"{name} on a drill is naive, so the recovery time measured from it is not"
                raise RecoveryError(msg)
        if self.finished_at < self.started_at:
            msg = "a drill finished before it started, which is a negative recovery time"
            raise RecoveryError(msg)
        if not self.into_scratch:
            msg = (
                "a drill restored into something other than a scratch target. "
                f"{A_DRILL_AGAINST_THE_LIVE_SYSTEM_IS_A_SCHEDULED_OUTAGE}"
            )
            raise RecoveryError(msg)
        seen = [one.check for one in self.checks]
        if len(seen) != len(set(seen)):
            msg = (
                "a drill ran the same check twice, and which result the verdict uses then "
                "depends on the order they happen to be in"
            )
            raise RecoveryError(msg)


#: Every check a drill must pass before the restore counts. Deliberately all of `Check`.
#:
#: There are no optional checks and a test holds this equal to the enum, so adding a member
#: to `Check` makes it required rather than letting it be declared and never asked.
REQUIRED_CHECKS: Final[tuple[Check, ...]] = (
    Check.SCHEMA_COMPLETE,
    Check.SMOKE_QUERY,
    Check.PERMISSION_CANARY,
)


@dataclass(frozen=True)
class Verification:
    """What a drill proved (M30.3.7, M30.3.8). Obtainable only from `verification_of`.

    Every combination that would let a reader believe more than was proved is refused in the
    constructor rather than left to a renderer: a verified result with shortfalls, a failed
    one with none, a recovery time on a drill that recovered nothing, and a verified drill
    with no recovery time to show.
    """

    backup_id: str
    attempted_at: datetime
    verified: bool
    #: Measured from the drill, in seconds, and present only when `verified`. See
    #: `A_DRILL_THAT_DID_NOT_VERIFY_HAS_NO_RECOVERY_TIME`.
    rto_seconds: float | None
    #: One sentence per required check that did not pass. Empty when `verified`.
    shortfalls: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.verified and self.shortfalls:
            msg = (
                f"backup {self.backup_id!r} is recorded as verified and carries "
                f"{len(self.shortfalls)} shortfall(s), so the flag and the reasons disagree"
            )
            raise RecoveryError(msg)
        if not self.verified and not self.shortfalls:
            msg = (
                f"backup {self.backup_id!r} did not verify and says nothing about why, "
                "which sends whoever reads it to look for a fault in the drill"
            )
            raise RecoveryError(msg)
        if self.verified and self.rto_seconds is None:
            msg = (
                f"backup {self.backup_id!r} verified and recorded no recovery time, which is "
                "the one number the drill exists to produce"
            )
            raise RecoveryError(msg)
        if not self.verified and self.rto_seconds is not None:
            msg = (
                f"backup {self.backup_id!r} did not verify and carries a recovery time of "
                f"{self.rto_seconds}s. {A_DRILL_THAT_DID_NOT_VERIFY_HAS_NO_RECOVERY_TIME}"
            )
            raise RecoveryError(msg)
        if self.rto_seconds is not None and self.rto_seconds < 0:
            msg = f"backup {self.backup_id!r} recovered in {self.rto_seconds}s"
            raise RecoveryError(msg)


def verification_of(drill: Drill) -> Verification:
    """What this drill proved, which is nothing unless every required check passed.

    A check that did not run is reported separately from one that ran and failed, and both
    are shortfalls. That distinction is the useful half: a drill missing the permission
    canary is a drill whose runner was misconfigured, and a drill whose permission canary
    failed is a restore that produced an open database. Collapsing them into "not verified"
    sends the same person to look at two very different things.

    The recovery time is the whole drill, from the restore starting to the last check
    finishing, because that is the interval before the copy could have been used.
    """
    ran = {one.check: one for one in drill.checks}
    shortfalls: list[str] = []
    for check in REQUIRED_CHECKS:
        found = ran.get(check)
        if found is None:
            shortfalls.append(
                f"{check.value} did not run, and a check nobody asked is not a check that passed"
            )
            continue
        if not found.passed:
            shortfalls.append(f"{check.value} ran and did not pass: {found.detail}")
    verified = not shortfalls
    return Verification(
        backup_id=drill.backup_id,
        attempted_at=drill.started_at,
        verified=verified,
        rto_seconds=(drill.finished_at - drill.started_at).total_seconds() if verified else None,
        shortfalls=tuple(shortfalls),
    )


def last_verified_restore(verifications: Sequence[Verification]) -> Verification | None:
    """The most recent restore that actually verified, or `None`.

    Failed attempts are not candidates, which is the entire point of the function: the field
    a console labels "last verified restore" must not move because somebody tried and
    failed, and the natural implementation sorting by `attempted_at` over everything does
    exactly that.
    """
    passed = [one for one in verifications if one.verified]
    if not passed:
        return None
    return max(passed, key=lambda one: (one.attempted_at, one.backup_id))


#: How often a restore is rehearsed, in days (M30.3.6).
#:
#: Weekly, and the figure is bounded from above by something outside itself:
#: `backup_policy_gaps` refuses a drill interval that is not shorter than
#: `BACKUP_RETENTION_DAYS`, because an interval longer than the window means a copy can be
#: written, retained, expired and deleted without anybody ever having read it back.
DRILL_INTERVAL_DAYS: Final[int] = 7


def drill_due(*, last_verified_at: datetime | None, now: datetime) -> bool:
    """Whether a restore rehearsal is owed (M30.3.6).

    `None` is due. A system that has never verified a restore is not between drills, it is
    a system whose backups have never been read, and treating an absent record as "not yet
    time" is how that state persists for a year.

    Shaped like `brain.ops.canaries.due` and `brain.models.health.due_probes`, and for the
    same reason: something else owns the schedule, and that something can be a worker tick,
    a cron entry or a test advancing a clock, and the third is why.
    """
    if now.tzinfo is None:
        msg = "a naive now decides a schedule at this machine's offset"
        raise RecoveryError(msg)
    if last_verified_at is None:
        return True
    if last_verified_at.tzinfo is None:
        msg = "a naive last verified time compares against an aware now by accident"
        raise RecoveryError(msg)
    return now - last_verified_at >= timedelta(days=DRILL_INTERVAL_DAYS)


# ------------------------------------------------------------------ the schedule
@dataclass(frozen=True)
class Scheduled:
    """One recurring copy: what it covers, how it is taken, and how often.

    The interval is what a recovery point objective is checked against, so it is a number
    here rather than a cron expression: `0 3 * * *` is a string this module would have to
    parse in order to know it means a day, and the parse is the part that goes wrong.
    """

    coverage: Coverage
    method: Method
    every_seconds: int
    because: str

    def __post_init__(self) -> None:
        if self.every_seconds < 1:
            msg = (
                f"a {self.method.value} copy of {self.coverage.value} on no interval is "
                "not a schedule"
            )
            raise RecoveryError(msg)
        if not self.because.strip():
            msg = (
                f"the {self.method.value} copy of {self.coverage.value} states no reason for "
                "its interval, and an unexplained interval is the one that gets lengthened"
            )
            raise RecoveryError(msg)


#: The default schedule (M30.3.1, M30.3.2). Continuous archiving plus daily incrementals and
#: weekly fulls for the database, hourly snapshots for everything else.
#:
#: **Nothing in this repository runs any of it.** This is the declaration a timer would be
#: written from and the input `backup_policy_gaps` checks the objectives against, which is
#: worth having before the timer exists precisely because the objectives were written first.
#:
#: The hourly figure for the object store and the configuration is not tidiness. It is what
#: the tightest profile's recovery point objective requires: see
#: `AN_RPO_IS_A_PROMISE_ABOUT_THE_SLOWEST_COPY`, and note that daily snapshots there would
#: make the full profile's stated hour unachievable while every database figure still looked
#: excellent.
SCHEDULE: Final[tuple[Scheduled, ...]] = (
    Scheduled(
        coverage=Coverage.DATABASE,
        method=Method.CONTINUOUS_WAL,
        every_seconds=60,
        because=(
            "a write-ahead segment is archived at least every minute whether or not it is "
            "full, so a database that is quiet does not accumulate an hour of exposure "
            "waiting for a segment to fill"
        ),
    ),
    Scheduled(
        coverage=Coverage.DATABASE,
        method=Method.INCREMENTAL,
        every_seconds=86_400,
        because=(
            "a daily incremental bounds how many archived segments a restore has to replay, "
            "which is the difference between a recovery time in minutes and one in hours"
        ),
    ),
    Scheduled(
        coverage=Coverage.DATABASE,
        method=Method.FULL,
        every_seconds=604_800,
        because=(
            "a weekly full bounds the incremental chain; a chain with no full at the bottom "
            "is a set of copies that restores nothing"
        ),
    ),
    Scheduled(
        coverage=Coverage.OBJECT_STORE,
        method=Method.SNAPSHOT,
        every_seconds=3_600,
        because=(
            "restic snapshots are content addressed, so an hourly run of a store that has "
            "not changed costs a listing, and the interval is what the tightest profile's "
            "recovery point objective is actually promising about uploaded documents"
        ),
    ),
    Scheduled(
        coverage=Coverage.CONFIGURATION,
        method=Method.SNAPSHOT,
        every_seconds=3_600,
        because=(
            "configuration changes rarely and matters entirely: an install restored with "
            "last month's realm and policies is a different install"
        ),
    ),
)


def scheduled_exposure_seconds(
    coverage: Coverage, schedule: Sequence[Scheduled] = SCHEDULE
) -> int | None:
    """The best exposure this schedule can produce for one coverage. `None` when unscheduled.

    The minimum interval rather than the sum or the mean: several copies of one thing on
    different intervals are protecting it together, and the exposure is decided by the most
    frequent of them.
    """
    intervals = [one.every_seconds for one in schedule if one.coverage is coverage]
    if not intervals:
        return None
    return min(intervals)


def worst_scheduled_exposure_seconds(schedule: Sequence[Scheduled] = SCHEDULE) -> int | None:
    """The exposure a single recovery point objective is actually promising. `None` if unset.

    The maximum over the coverages, which is the arithmetic
    `AN_RPO_IS_A_PROMISE_ABOUT_THE_SLOWEST_COPY` describes. A coverage nothing schedules is
    not counted here and is reported by `backup_policy_gaps` instead, because an unbounded
    exposure and a slow one are different findings and only one of them is a number.
    """
    each = [scheduled_exposure_seconds(kind, schedule) for kind in Coverage]
    measured = [one for one in each if one is not None]
    if not measured:
        return None
    return max(measured)


# ------------------------------------------------------------------ the retention ladder
#: Days in a week, and the longest a month gets. Both used to age the ladder upward.
#:
#: Thirty-one rather than thirty, and rather than an average. The ladder's horizon feeds a
#: comparison against what an erasure certificate promises, and a horizon computed a day
#: short would make the conflict look one day smaller than it is. Rounding a retention
#: window down is the direction that produces a document saying data is gone while a copy
#: of it is still on a shelf.
DAYS_IN_A_WEEK: Final[int] = 7
LONGEST_MONTH_DAYS: Final[int] = 31


@dataclass(frozen=True)
class Ladder:
    """How many copies of each period are kept."""

    daily: int
    weekly: int
    monthly: int

    def __post_init__(self) -> None:
        for name in ("daily", "weekly", "monthly"):
            count: int = getattr(self, name)
            if count < 0:
                msg = f"a ladder keeping {count} {name} copies is not a retention policy"
                raise RecoveryError(msg)
        if self.daily + self.weekly + self.monthly < 1:
            msg = "a ladder that keeps nothing is a deletion policy wearing a backup's name"
            raise RecoveryError(msg)

    def horizon_days(self) -> int:
        """How old the oldest copy this ladder keeps can be, in days.

        The maximum of the three rungs rather than their sum. The rungs overlap: yesterday's
        copy is a daily and, one day a week, also a weekly, so adding them counts the same
        backup up to three times and produces a horizon far beyond anything retained.
        """
        return max(
            self.daily,
            self.weekly * DAYS_IN_A_WEEK,
            self.monthly * LONGEST_MONTH_DAYS,
        )


#: The ladder M30.3.5 asks for, declared and deliberately not applied to anything.
#:
#: See `THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES`. `backup_policy_gaps`
#: reports the conflict against `BACKUP_RETENTION_DAYS` and there is no pruning function
#: here, because pruning to this ladder is the act that makes the certificates wrong.
RETENTION_LADDER: Final[Ladder] = Ladder(daily=30, weekly=12, monthly=12)


def backup_policy_gaps(
    *,
    ladder: Ladder = RETENTION_LADDER,
    horizon_days: int = BACKUP_RETENTION_DAYS,
    drill_interval_days: int = DRILL_INTERVAL_DAYS,
    objectives: Sequence[RecoveryObjective] | None = None,
    schedule: Sequence[Scheduled] = SCHEDULE,
) -> tuple[str, ...]:
    """Everything about the declared backup policy that does not hold together.

    Every input is a parameter defaulting to this module's own, for the reason
    `brain.ops.erasure.erasure_gaps` takes the same shape: a check that can only be run
    against the healthy declaration cannot be shown to fail, and one nobody has seen fail is
    one nobody knows works. It is also how a client's own figures are checked, which is the
    point of `THE_NEXT_COMPANY_KEEPS_ITS_OWN_COPIES_FOR_ITS_OWN_REASONS`.

    Four families, in the order they cost somebody something: a retention ladder that
    outlives the promise made to a person who asked to be forgotten, a rehearsal interval
    that lets a copy expire unread, a coverage nothing is scheduled to copy, and a recovery
    point objective the schedule cannot meet.
    """
    findings: list[str] = []

    reach = ladder.horizon_days()
    if reach > horizon_days:
        findings.append(
            f"the retention ladder keeps a copy for up to {reach} days and every erasure "
            f"certificate promises the data is beyond backup reach after {horizon_days}. "
            f"{THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES}"
        )
    if drill_interval_days >= horizon_days:
        findings.append(
            f"a restore is rehearsed every {drill_interval_days} days against a window of "
            f"{horizon_days}, so a copy can be written, kept, expired and deleted without "
            "anybody having read it back once"
        )

    for kind in Coverage:
        if scheduled_exposure_seconds(kind, schedule) is None:
            findings.append(
                f"nothing is scheduled to copy {kind.value}, so its recovery point is "
                "whenever somebody last did it by hand"
            )

    slowest = worst_scheduled_exposure_seconds(schedule)
    considered = RECOVERY_OBJECTIVES if objectives is None else tuple(objectives)
    if slowest is not None:
        findings.extend(
            f"the {one.profile} profile promises a recovery point of {one.rpo_seconds}s and "
            f"the slowest thing on the schedule is copied every {slowest}s. "
            f"{AN_RPO_IS_A_PROMISE_ABOUT_THE_SLOWEST_COPY}"
            for one in considered
            if one.rpo_seconds < slowest
        )
    return tuple(findings)


# ------------------------------------------------------------------------ alerting
@dataclass(frozen=True)
class Alert:
    """One thing worth waking somebody for, and how loudly.

    Names the coverage and never a record, a field or a count of anything hidden. A backup
    alert is read by whoever is on call, who is not necessarily entitled to what the backup
    contains, and the shape rule `brain.ops.denial_alerts` keeps applies unchanged.
    """

    severity: Severity
    coverage: Coverage | None
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            msg = "an alert with no text wakes somebody up to look at a blank line"
            raise RecoveryError(msg)


def alerts(
    *,
    backups: Sequence[Backup],
    verifications: Sequence[Verification],
    profile: str,
    now: datetime,
    objectives: Sequence[RecoveryObjective] | None = None,
) -> tuple[Alert, ...]:
    """What is currently worth an alert (M30.3.10, M30.3.11), loudest first.

    Two families. A coverage whose exposure is past the profile's recovery point objective,
    including one that has never been copied at all, and a drill that ran and did not verify.
    The second is louder because it is a statement about every copy held rather than about
    one of them: a failed verification does not mean the newest backup is bad, it means
    nobody knows whether any of them is readable.

    Sorted by severity descending so the reader's first line is the worst one. A list in
    declaration order puts an aged object store above a failed verification whenever the
    coverages happen to iterate first, and an operator triaging at 3am reads down.
    """
    target = recovery_objective(profile, objectives)
    found: list[Alert] = []
    for kind in Coverage:
        exposure = exposure_seconds(backups, kind, now=now)
        if exposure is None:
            found.append(
                Alert(
                    severity=Severity.BACKUP_AGED,
                    coverage=kind,
                    text=(
                        f"no copy of {kind.value} exists at all, so the recovery point for "
                        "it is the day the install was built"
                    ),
                )
            )
            continue
        if exposure > target.rpo_seconds:
            found.append(
                Alert(
                    severity=Severity.BACKUP_AGED,
                    coverage=kind,
                    text=(
                        f"{kind.value} is {exposure:.0f}s behind against a recovery point "
                        f"objective of {target.rpo_seconds}s on the {profile} profile"
                    ),
                )
            )
    found.extend(
        Alert(
            severity=Severity.VERIFICATION_FAILED,
            coverage=None,
            text=(
                f"a restore of {one.backup_id} was attempted and did not verify: "
                f"{'; '.join(one.shortfalls)}. Until one does, no copy held is known to be "
                "readable"
            ),
        )
        for one in verifications
        if not one.verified
    )
    return tuple(sorted(found, key=lambda one: -one.severity))
