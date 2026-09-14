"""The backup and recovery panel: the screen somebody checks before deciding not to worry.

This is the screen `docs/needs-rupash.md` item 44 says is deliberately not built, and the test
that kept it unbuilt is a tripwire rather than a rule: it asserts that nothing produces a
verified restore, and its own failure message reads "the recovery panel can now be built".
`brain.ops.backup_manifest.read_drills` produces one, so the condition has been met and this is
the screen. The argument for changing that pin is in `tests/unit/test_installation.py` beside
the assertion that replaced it.

**A backup timestamp beside an empty "last verified restore" is the most reassuring shape of
the worst state this system has.** Every indicator green, a copy taken three hours ago, and
nobody has ever read one back, which is the exact position this product is in today. The blank
field is what makes it reassuring: a renderer handed `None` draws a dash, a dash reads as not
applicable, and the reader stops looking. So there is no state in which this panel hands a
renderer a blank. `last_verified_fact` is a `brain.console.installation.Fact`, which refuses an
unknown value carrying a string and requires a sentence saying why nothing is known, and
`answer` is two sentences from `ANSWERS` which is total over `Assurance`. See
`A_FRESH_BACKUP_BESIDE_A_BLANK_VERIFIED_FIELD_IS_THE_WORST_STATE_LOOKING_BEST`.

**An unverified install renders `NEVER_VERIFIED`, in words, with the backup ages beside it, and
the backup being fresh does not soften it.** That is the decision this module is asked to
argue. The alternative shapes were: no panel at all, which leaves the reader with nothing and
was the position until today; a panel that hides the backup ages until a drill has run, which
throws away the one measurement that exists; and a panel that scores the two independently, a
tick for the copies and a blank for the drill, which is the failure above. What is built shows
both numbers and one verdict computed from both, and the verdict is the pessimistic one,
because the copies' freshness is evidence about the taker and no evidence at all about whether
any of them can be read.

**The field and the verdict are two questions, and a later failure does not move the field.**
`brain.ops.recovery.last_verified_restore` is written so a failed drill cannot advance it,
which is right: the field says when a restore last verified. It therefore goes on saying Monday
after Tuesday's drill failed, and on Tuesday evening nothing this install holds is known to be
readable. `last_attempt` is the second question and `Panel` refuses the reassuring answer
unless the newest attempt is itself the verified one. A panel built on the field alone renders
a date and a tick on the evening of a failure.

**The reassuring answer carries every condition and the others carry none.** `SETTLED` holds
one member and `Panel.__post_init__` refuses it without copies, without a verification, with a
newer failed attempt, with a drill overdue, with a coverage outside the profile's recovery
point, or with any record in the bucket that could not be read. Stating one of the other seven
answers too firmly costs a reader nothing, which is the asymmetry
`brain.console.version_view.Panel` keeps for the same reason on the screen next door.

**An unreadable record refuses the tick rather than being counted around it.** Dropping what
cannot be parsed is safe in six of the eight answers, because a missing copy makes the exposure
read older and a missing success makes the drill read overdue, and both are alarming. It is not
safe in the seventh: a truncated record of the drill that fell over leaves last month's success
standing as the newest evidence, which moves the panel in the flattering direction. So an
unreadable record is asked first and is its own answer, and the files are named so somebody can
go and look. See `AN_UNREADABLE_RECORD_MOVES_THIS_PANEL_THE_FLATTERING_WAY`.

**Nothing on this panel counts what a reader may not see, and nothing here narrows by reach.**
The rows are the three coverages, always all three, and the absence of a copy is a row that
says so rather than a row left out: a screen that showed two rows where a healthy install shows
three would be reporting the absence by subtraction. The subjects are the install's own copies
and no row names a person, a department or a record, so unlike
`brain.console.installation.throttled_now` there is nothing here to intersect and the module
holds no `EntitlementSet` at all. Who may open the screen is
`brain.console.screens`'s question and it answers it with `read:backup`.

**The reassuring answer is never reachable in a state where the client's own service level
statement would be refused.** `brain.launch.service_level` refuses to render a statement that
promises a recovery point the schedule cannot deliver, one the copies cannot deliver, a
recovery time no drill measured, or one the last drill exceeded. A console saying recoverable
while the document a client signs refuses is two answers to one question, and the console is
the one somebody reads. `SLOWER_THAN_PROMISED` exists for the last of those refusals and for no
other reason, and a test holds the whole relation rather than this paragraph doing it.

**That sentence was false for the first refusal until the test was written.** Every row was
judged on its newest copy alone, so a schedule copying the object store every two hours under
a promise of one, with a copy from half an hour ago, was recoverable; and an empty schedule
made every coverage unexpected, which left no row to decide over and answered recoverable
about an install holding no copies at all. A copy is the fact and the schedule is the
intention, and a recovery point needs both: a row is inside its objective only when the
schedule keeps it there, and a schedule copying nothing makes every row count. See
`_rows_that_decide`.

Rejected: a table for drill results and a migration to hold it. The record would be in the
database the drill exists to prove is replaceable, so it is unreadable in the hour it is for,
which `brain.ops.backup_manifest`'s header argues at length. No migration was written.

Rejected: a `verified: bool` on this panel. A boolean is what a renderer draws as a tick, and
every one of the seven unreassuring answers would collapse into its false branch, which draws
the same grey nothing for "a drill failed last night" and "a drill is three days overdue".

Rejected: an `Answer` of this module's own. `brain.console.version_view.Answer` is the pair of
sentences a client reads for one state, and the two screens sit in the same console group and
are read by the same person: a second pair type is how one screen comes to say what to do and
its neighbour comes to say only what is wrong. Its refusals raise `VersionError`, which is
named here so a reader meeting one is not surprised.

Rejected: reading the bucket. Every observation is a parameter, for the reason the whole of
`brain.ops.recovery` takes its observations that way: the interesting cases are an install with
no copies and a bucket with a truncated record, and neither can be reached through a module
that opens an object store.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything, and
nothing here writes. The one-click drill `brain.console.screens` describes is a write and no
console module performs one; what the panel answers is whether a drill is owed and what the
last one proved. M30.3.9 is therefore not claimed.

Task ids: M27.6.2
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.console.installation import Fact, Source
from brain.console.version_view import Answer
from brain.ops.backup_manifest import Unreadable
from brain.ops.recovery import (
    SCHEDULE,
    Backup,
    Coverage,
    Scheduled,
    Verification,
    drill_due,
    exposure_seconds,
    last_attempt,
    last_verified_restore,
    latest,
    scheduled_exposure_seconds,
)
from brain.ops.reliability import RecoveryObjective, recovery_objective


class RecoveryViewError(Exception):
    """Raised when this panel would state an install's recoverability more firmly than known."""


# ------------------------------------------------------------------- written-down reasons
#: Why a blank verified field is worse than a loud one.
A_FRESH_BACKUP_BESIDE_A_BLANK_VERIFIED_FIELD_IS_THE_WORST_STATE_LOOKING_BEST: Final = (
    "An install whose nightly copy has run perfectly for a month and whose backups nobody "
    "has ever read back shows a recent timestamp, a plausible size and an empty field under "
    "last verified restore. A renderer draws the empty field as a dash, a dash reads as not "
    "applicable, and the reader has now checked the screen and stopped. That is the worst "
    "state this system has, wearing the appearance of the best one, and the appearance comes "
    "entirely from the blank. So nothing on this panel is blank: an unknown fact carries a "
    "sentence saying what would have to happen for it to be known, and the verdict over the "
    "whole panel is the pessimistic one whenever the copies are fresh and unproven."
)

#: Why a record that could not be parsed is its own answer rather than a file skipped.
AN_UNREADABLE_RECORD_MOVES_THIS_PANEL_THE_FLATTERING_WAY: Final = (
    "Dropping what cannot be read is usually safe here, because a lost copy makes the "
    "exposure read older and a lost success makes a drill read overdue, and both of those "
    "are alarming. It is not safe for a failed drill: the run that fell over is the run "
    "whose record is truncated, and losing it leaves an older success standing as the newest "
    "evidence, which is the one direction a panel read before deciding not to worry must "
    "never move in. So an unreadable record is asked before every other question, the answer "
    "is that nothing below is known to be about the whole bucket, and the files are named."
)

#: Why the copies and the drill are one verdict rather than two indicators.
A_COPY_BEING_FRESH_IS_EVIDENCE_ABOUT_THE_TAKER_AND_NOT_ABOUT_THE_COPY: Final = (
    "The age of the newest copy says the thing that takes copies ran. It says nothing about "
    "whether the artefact is complete, whether the key that encrypted it still exists, or "
    "whether the source it was taken from had stopped replicating, and every one of those "
    "produces a recent object of a plausible size. Two indicators side by side let a reader "
    "take the green one as the answer and the grey one as a detail, so there is one verdict "
    "and it is computed from both, and the freshness of an unproven copy never improves it."
)

#: Why a console verdict and the document a client signs must not disagree.
A_SCREEN_SAYING_RECOVERABLE_OVER_A_STATEMENT_THAT_REFUSES_IS_TWO_ANSWERS: Final = (
    "brain.launch.service_level refuses to render a service level statement promising a "
    "recovery point the schedule cannot deliver or the copies that exist cannot, a recovery "
    "time no drill has measured, or one the last drill exceeded. If this panel can say "
    "recoverable in a state where that document refuses, the install has two answers to one "
    "question and the one somebody reads is the screen. Every refusal in that function is "
    "therefore reachable from an answer here, and the last of them is the only reason "
    "SLOWER_THAN_PROMISED is a member at all."
)


# ------------------------------------------------------------- what is known about one copy
#: The two statements a reader gets about each coverage, as they are named on the screen.
#:
#: Two rather than one, and the split is `A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT`
#: from `brain.launch` put on a screen: the interval is what this install means to do and the
#: newest copy is what it has done, and a panel showing only the first passed a client's whole
#: service level statement on an estate holding no copies whatsoever.
SCHEDULE_FACT: Final = "copied every"
NEWEST_FACT: Final = "newest copy reaches"


@dataclass(frozen=True)
class CopyState:
    """What is known about copies of one coverage: the intention, and the fact.

    `within_objective` is a property rather than a field, and that is the load-bearing
    decision in this class. A stored boolean is a slot in which a coverage with no copy at all
    can be recorded as inside its recovery point, which is an absence rendered as compliance,
    and it would be set by whoever assembled the row rather than by the arithmetic. There is no
    way to construct a row here that says a coverage nothing has copied is within anything.

    There is no refusal of a negative exposure. `brain.ops.recovery.exposure_seconds` refuses a
    copy that restores to a moment which has not happened, which is the clock disagreement that
    produces one, and it says so better than a second check here would. A duplicate guard in
    this position could not fire, which is the defect `CLAUDE.md` names as this repository's
    commonest.
    """

    coverage: Coverage
    #: The newest copy that exists, or `None` when nothing has ever copied this.
    newest: Backup | None
    #: How often the schedule means to copy this, in seconds. `None` when nothing schedules it.
    scheduled_every_seconds: int | None
    #: How far behind the newest copy leaves this coverage, in seconds. `None` when no copy.
    measured_exposure_seconds: float | None
    #: The profile's recovery point, carried so the comparison is not made somewhere else.
    objective_seconds: int

    def __post_init__(self) -> None:
        if self.newest is None and self.measured_exposure_seconds is not None:
            msg = (
                f"{self.coverage.value} has no copy and carries an exposure of "
                f"{self.measured_exposure_seconds}s, which is a measurement of nothing"
            )
            raise RecoveryViewError(msg)
        if self.newest is not None and self.measured_exposure_seconds is None:
            msg = (
                f"{self.coverage.value} has a copy reaching {self.newest.recoverable_to} and "
                "no exposure measured from it, so the row would render as never copied"
            )
            raise RecoveryViewError(msg)
        if self.objective_seconds < 1:
            msg = (
                f"{self.coverage.value} is measured against a recovery point of "
                f"{self.objective_seconds}s, which no copy can ever be inside"
            )
            raise RecoveryViewError(msg)

    @property
    def within_objective(self) -> bool:
        """Whether this coverage is inside the profile's recovery point and scheduled to stay so.

        A coverage with no copy is outside it. Not because nothing was measured, but because
        the exposure on something nothing has copied is unbounded rather than large, which is
        the distinction `brain.launch.A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT` draws
        and which a `None` compared against a number would quietly lose.

        **A copy inside the recovery point today is outside it when the schedule cannot keep it
        there**, and a coverage nothing schedules is outside it however fresh its copy. The
        copy is the fact and the schedule is the intention, and `brain.launch.service_level`
        refuses a promise either one cannot deliver. Judged on the copy alone, a schedule
        copying the object store every two hours under a promise of one was recoverable in the
        half hour after each copy, beside a statement refusing to render.
        """
        if self.measured_exposure_seconds is None or self.scheduled_every_seconds is None:
            return False
        return (
            self.measured_exposure_seconds <= self.objective_seconds
            and self.scheduled_every_seconds <= self.objective_seconds
        )

    @property
    def facts(self) -> tuple[Fact, ...]:
        """The two labelled statements a renderer shows for this coverage, in that order.

        Both are always present. A coverage nothing schedules and nothing has copied is two
        rows saying so, which is a reader being told, where leaving it out is a reader
        counting the rows and finding three where a healthy install shows three.
        """
        return (self._schedule_fact(), self._newest_fact())

    def _schedule_fact(self) -> Fact:
        """What this install means to do about this coverage, which is a declaration."""
        if self.scheduled_every_seconds is None:
            return Fact(
                name=f"{self.coverage.value}: {SCHEDULE_FACT}",
                source=Source.UNKNOWN,
                because=(
                    "nothing is scheduled to copy this at all, so its recovery point is "
                    "whenever somebody last did it by hand"
                ),
            )
        return Fact(
            name=f"{self.coverage.value}: {SCHEDULE_FACT}",
            source=Source.DECLARED,
            value=f"{self.scheduled_every_seconds}s",
            because=(
                "the interval the schedule declares. It is what this install means to do "
                "rather than what it has done, and the copy below is the second half"
            ),
        )

    def _newest_fact(self) -> Fact:
        """What has actually been copied, which is the only half a recovery rests on."""
        if self.newest is None:
            return Fact(
                name=f"{self.coverage.value}: {NEWEST_FACT}",
                source=Source.UNKNOWN,
                because=(
                    "nothing has ever copied this, so the exposure on it is not a large "
                    "number, it is unbounded, and losing it means losing all of it"
                ),
            )
        return Fact(
            name=f"{self.coverage.value}: {NEWEST_FACT}",
            source=Source.MEASURED,
            value=self.newest.recoverable_to.isoformat(),
            because=(
                "the furthest forward any copy of this can restore to. A copy nobody has "
                "read back is a file, so this is a statement about what was written rather "
                "than about what can be recovered"
            ),
        )


def copy_states(
    backups: Sequence[Backup],
    *,
    profile: str,
    now: datetime,
    schedule: Sequence[Scheduled] = SCHEDULE,
    objectives: Sequence[RecoveryObjective] | None = None,
) -> tuple[CopyState, ...]:
    """One row per coverage, in declaration order, always all of them (M27.6.2).

    Every coverage gets a row whether or not anything copies it and whether or not anything
    schedules it. A coverage left out is an absence a reader would have to notice by counting,
    and the whole of this screen is about absences that read as blanks.

    `exposure_seconds` is allowed to raise rather than being caught and rendered. A copy that
    restores to a moment which has not happened means two clocks disagree, and the exposure
    computed past it reads smaller than the truth, which is the direction this panel exists to
    refuse. A screen that fails to draw sends somebody to look; a screen drawing a healthier
    number than the truth does not.
    """
    objective = recovery_objective(profile, objectives)
    rows: list[CopyState] = []
    for coverage in Coverage:
        newest = latest(backups, coverage)
        rows.append(
            CopyState(
                coverage=coverage,
                newest=newest,
                scheduled_every_seconds=scheduled_exposure_seconds(coverage, schedule),
                measured_exposure_seconds=exposure_seconds(backups, coverage, now=now),
                objective_seconds=objective.rpo_seconds,
            )
        )
    return tuple(rows)


def _rows_that_decide(copies: Sequence[CopyState]) -> tuple[CopyState, ...]:
    """The rows a verdict is decided over: those the schedule copies, or all of them if none.

    A coverage the schedule does not copy is `backup_policy_gaps`'s finding rather than this
    panel's, for the reason `assurance_of` gives. **A schedule that copies nothing at all is
    not that case taken three times.** Read that way it leaves no row to decide over, and a
    verdict over no rows passed every question and answered recoverable about an install
    holding no copies, beside a service level statement refusing because nothing is scheduled.
    So when nothing is scheduled every row counts, and `CopyState.within_objective` is false on
    a row nothing schedules, which is the same refusal arriving as an aged copy.

    Shared by `assurance_of` and `Panel`, because two copies of which rows count is how a
    verdict and the refusal on it come to disagree.
    """
    scheduled = tuple(one for one in copies if one.scheduled_every_seconds is not None)
    return scheduled or tuple(copies)


# ---------------------------------------------------------------- where this install stands
class Assurance(enum.StrEnum):
    """Whether this install can be recovered, in one word, with every way of not knowing kept
    apart.

    Eight rather than two, for the reason `brain.console.version_view.Standing` has seven: the
    two-answer version of this screen is a tick and the absence of one, and the absence of a
    tick is read as a tick that has not loaded yet. Every member has a producer in
    `assurance_of` and a pair of sentences in `ANSWERS`.
    """

    #: Something in the bucket could not be read, so every answer below is about a subset
    #: nobody chose. Asked first because it is the only one true regardless of the rest.
    RECORDS_UNREADABLE = "records unreadable"
    #: Something the schedule covers has no copy at all. There is nothing to verify.
    NOTHING_COPIED = "nothing copied"
    #: The most recent drill ran and did not verify, whatever an earlier one proved.
    VERIFICATION_FAILED = "verification failed"
    #: No drill has ever verified, so no copy this install holds has been read back.
    NEVER_VERIFIED = "never verified"
    #: A copy is further behind than the profile's recovery point promises, or the schedule
    #: behind one cannot keep it inside that promise.
    BACKUP_AGED = "backup aged"
    #: A restore verified, longer ago than the rehearsal interval allows.
    DRILL_OVERDUE = "drill overdue"
    #: A restore verified, and took longer than the profile's recovery time promises.
    SLOWER_THAN_PROMISED = "slower than promised"
    #: Copied, read back, recently, inside both figures. The only reassuring answer.
    RECOVERABLE = "recoverable"


#: The answers a renderer may draw as reassurance, and there is exactly one.
#:
#: A set rather than a flag on each member, so the question "which of these is a tick" is asked
#: in one place and a member added later is outside it by default. This is
#: `brain.console.version_view.SETTLED`'s construction and the reason is the same, with one
#: addition: `Panel` refuses every member of this set that its conditions do not support, so
#: widening the set widens what has to be proved rather than what may be claimed.
SETTLED: Final[frozenset[Assurance]] = frozenset({Assurance.RECOVERABLE})


#: The two sentences for every answer. Complete over `Assurance`, and a test holds that.
#:
#: Written for somebody with a server and no source tree, which is why none of them names a
#: module, a function or a task id.
ANSWERS: Final[Mapping[Assurance, Answer]] = MappingProxyType(
    {
        Assurance.RECORDS_UNREADABLE: Answer(
            says=(
                "At least one of the records describing your copies or your recovery "
                "rehearsals could not be read, so everything else on this screen is about "
                "whatever could. The run that fails halfway is the run whose record is "
                "truncated, so the missing one is the one most likely to matter."
            ),
            what_to_do=(
                "Look at the files named beside this. Each one is in the same place as the "
                "copies themselves. Until they are readable or gone, treat nothing on this "
                "screen as a statement about all of your copies."
            ),
        ),
        Assurance.NOTHING_COPIED: Answer(
            says=(
                "Something this install is meant to copy has never been copied at all. That "
                "is not a large amount of exposure, it is unbounded: if it is lost today, all "
                "of it is lost."
            ),
            what_to_do=(
                "Look at the rows above for the one with no copy, and get something copying "
                "it. Nothing else on this screen is worth much until every row has a copy "
                "behind it."
            ),
        ),
        Assurance.VERIFICATION_FAILED: Answer(
            says=(
                "The most recent rehearsal restored a copy and the restored copy failed at "
                "least one of its checks. Until one passes, no copy you hold is known to be "
                "readable, whatever an earlier rehearsal proved. If the check that failed was "
                "the permission one, the restored copy answered questions it should have "
                "refused, which is worse than it not restoring."
            ),
            what_to_do=(
                "Read what the failed check reported, fix it, and rehearse again. Do not "
                "treat the date beside last verified restore as current: it is when a restore "
                "last worked, not a statement about your copies today."
            ),
        ),
        Assurance.NEVER_VERIFIED: Answer(
            says=(
                "No copy this install holds has ever been restored and checked. A copy nobody "
                "has read back is a file: a truncated dump, a dump encrypted with a key "
                "nobody has, and a dump taken from a source that had stopped updating all "
                "look exactly like a healthy one in a listing. The dates above tell you the "
                "thing that takes copies ran. They say nothing about whether any of them can "
                "be used."
            ),
            what_to_do=(
                "Rehearse a restore: load the newest copy into a scratch database, check the "
                "schema is complete, ask it a question you know the answer to, and check it "
                "still refuses something it should refuse. Until that has happened once, "
                "assume you cannot recover."
            ),
        ),
        Assurance.BACKUP_AGED: Answer(
            says=(
                "A copy is further behind than the recovery point this install's profile "
                "promises, or nothing copies it often enough to stay inside that promise, so "
                "more recent work than you have agreed to lose exists, or soon will, in only "
                "one place."
            ),
            what_to_do=(
                "Look at the rows above for the coverage whose newest copy is oldest or whose "
                "interval is longest. A copy that is late usually means a timer that is not "
                "enabled or a destination refusing writes. An interval longer than the promise, "
                "or no interval at all, means the schedule has to change or the promise does."
            ),
        ),
        Assurance.DRILL_OVERDUE: Answer(
            says=(
                "A restore has been verified here, and it was longer ago than the rehearsal "
                "interval. Everything copied since then is of unproven readability, and a "
                "copy that started failing the week after the last rehearsal looks exactly "
                "like this."
            ),
            what_to_do=(
                "Rehearse a restore again. The value of a rehearsal is that it was recent: an "
                "old one proves the copies of that week could be read."
            ),
        ),
        Assurance.SLOWER_THAN_PROMISED: Answer(
            says=(
                "A restore was verified recently and it took longer than the recovery time "
                "this install's profile promises. Your copies are readable. The figure in "
                "your agreement is one somebody has now watched this system miss."
            ),
            what_to_do=(
                "Either make the restore faster or change the figure you promise. Until one "
                "of the two happens, the service level statement for this profile will refuse "
                "to render rather than state a time the last rehearsal exceeded."
            ),
        ),
        Assurance.RECOVERABLE: Answer(
            says=(
                "Every coverage the schedule copies has a copy inside the recovery point this "
                "profile promises and is copied often enough to stay there, a restore has been "
                "verified recently, it passed every check "
                "including the one about refusing what it should refuse, and it finished "
                "inside the recovery time promised. This is as strong as this screen gets and "
                "it is a statement about the last rehearsal rather than a guarantee about the "
                "next incident."
            ),
            what_to_do=(
                "Nothing today. Keep rehearsing on the interval: everything above is true of "
                "the copies that were checked, and the next one to go wrong will not announce "
                "itself."
            ),
        ),
    }
)


def assurance_of(
    copies: Sequence[CopyState],
    verifications: Sequence[Verification],
    *,
    objective: RecoveryObjective,
    now: datetime,
    unreadable: Sequence[Unreadable] = (),
) -> Assurance:
    """Where this install stands on being able to recover, in one word (M27.6.2).

    **The order of the questions is the argument and it is the whole function.** An unreadable
    record is asked first because it is the only answer that is true whatever the records
    below would have said; see
    `AN_UNREADABLE_RECORD_MOVES_THIS_PANEL_THE_FLATTERING_WAY`. A coverage with
    no copy is next, because a rehearsal has nothing to read and every answer about
    verification would be about the other coverages. Then the two states in which nothing held
    is known to be readable, the failed rehearsal ahead of the absent one because it names a
    fault somebody can chase today and because the fault may be a restored copy that refuses
    nothing. Then an aged copy, which is a bounded loss measured in the profile's own units.
    Then a rehearsal going stale, then one that was slower than promised.

    A coverage nothing is scheduled to copy is not a finding here. `backup_policy_gaps` reports
    it, with the remedy being to fix the schedule rather than to take a copy, and
    `brain.launch.service_level` skips the same coverages for the same reason: a console and
    the document a client signs disagreeing about which coverages count is two answers to one
    question. The exception is a schedule copying nothing at all, which that function refuses
    outright; see `_rows_that_decide`.

    `now` is a parameter for the reason every clock in `brain.ops.recovery` is one: the
    interesting case is the boundary and it cannot be reached through a function that reads the
    process clock.
    """
    if now.tzinfo is None:
        msg = "a naive now decides how stale a rehearsal is at this machine's offset"
        raise RecoveryViewError(msg)
    if unreadable:
        return Assurance.RECORDS_UNREADABLE
    expected = _rows_that_decide(copies)
    if not expected or any(one.newest is None for one in expected):
        return Assurance.NOTHING_COPIED
    attempt = last_attempt(verifications)
    if attempt is not None and not attempt.verified:
        return Assurance.VERIFICATION_FAILED
    verified = last_verified_restore(verifications)
    if verified is None:
        return Assurance.NEVER_VERIFIED
    if any(not one.within_objective for one in expected):
        return Assurance.BACKUP_AGED
    if drill_due(last_verified_at=verified.attempted_at, now=now):
        return Assurance.DRILL_OVERDUE
    # `Verification` refuses a verified result with no recovery time, so the `None` branch is
    # unreachable through that type. It is written as a comparison that a missing figure loses
    # rather than as an assertion, because the alternative is a verdict of recoverable resting
    # on a number nobody has.
    if verified.rto_seconds is None or verified.rto_seconds > objective.rto_seconds:
        return Assurance.SLOWER_THAN_PROMISED
    return Assurance.RECOVERABLE


# ------------------------------------------------------------------------------- the panel
#: The field this whole screen is named after, as a person reads it.
LAST_VERIFIED_FACT: Final = "last verified restore"


@dataclass(frozen=True)
class Panel:
    """The backup and recovery panel: what exists, what was proved, and where that leaves it.

    **The refusals are on the reassuring answer alone**, which is the same asymmetry
    `brain.console.version_view.Panel` keeps: every other member states that something is not
    known or not current, and stating one of those too firmly costs a reader nothing.

    `answer` is not optional decoration beside `assurance`. The word alone is a label three
    people read three ways, and the one word this panel most needs explaining is the one that
    describes an install with perfect backups nobody has read back.
    """

    profile: str
    copies: tuple[CopyState, ...]
    #: The most recent restore that verified. `None` when none ever has.
    last_verified: Verification | None
    #: The most recent rehearsal outcome whatever it proved. `None` when none has run.
    latest_attempt: Verification | None
    assurance: Assurance
    #: Whether a rehearsal is owed. `True` on an install that has never run one.
    drill_is_due: bool
    #: Every record in the bucket that could not be read, named so somebody can look.
    unreadable: tuple[Unreadable, ...] = ()

    def __post_init__(self) -> None:
        if self.assurance not in SETTLED:
            return
        if not self.copies:
            msg = (
                f"{self.assurance.value} is claimed and this panel knows about no copies at "
                "all, so the reassuring answer would be about an install nobody measured"
            )
            raise RecoveryViewError(msg)
        if self.unreadable:
            named = ", ".join(sorted(one.where for one in self.unreadable))
            msg = (
                f"{self.assurance.value} is claimed and the bucket holds a record that could "
                f"not be read ({named}), so the answer is about whichever ones happened to "
                f"parse. {AN_UNREADABLE_RECORD_MOVES_THIS_PANEL_THE_FLATTERING_WAY}"
            )
            raise RecoveryViewError(msg)
        if self.last_verified is None:
            msg = (
                f"{self.assurance.value} is claimed and no restore has ever verified here. "
                f"{A_FRESH_BACKUP_BESIDE_A_BLANK_VERIFIED_FIELD_IS_THE_WORST_STATE_LOOKING_BEST}"
            )
            raise RecoveryViewError(msg)
        if self.latest_attempt is None or not self.latest_attempt.verified:
            msg = (
                f"{self.assurance.value} is claimed and the most recent rehearsal did not "
                "verify, so the date beside last verified restore is when one last worked "
                "rather than a statement about the copies held now"
            )
            raise RecoveryViewError(msg)
        if self.drill_is_due:
            msg = (
                f"{self.assurance.value} is claimed and a rehearsal is overdue, so the "
                "reassurance rests on a restore nobody has repeated inside the interval"
            )
            raise RecoveryViewError(msg)
        outside = [
            one.coverage.value for one in _rows_that_decide(self.copies) if not one.within_objective
        ]
        if outside:
            msg = (
                f"{self.assurance.value} is claimed and {', '.join(outside)} is outside the "
                f"recovery point the {self.profile} profile promises, or is not copied often "
                "enough to stay inside it"
            )
            raise RecoveryViewError(msg)

    @property
    def answer(self) -> Answer:
        """The two sentences a client reads. Never assembled by whatever draws this."""
        return ANSWERS[self.assurance]

    @property
    def last_verified_fact(self) -> Fact:
        """The field this screen is named after, as a labelled statement rather than a slot.

        A `Fact` and not the `Verification | None` beside it, because `None` in a typed slot is
        where a renderer supplies a dash, and a dash under this heading beside a fresh backup
        timestamp is the reassuring blank this module exists to refuse. `Fact` refuses an
        unknown value carrying a string and requires a sentence saying why nothing is known.

        When a later rehearsal failed, the date is still the date and the sentence beside it
        says so. That is the one place this panel's two questions meet in a single field, and
        it is written this way so that a renderer showing the field without the verdict still
        does not mislead.
        """
        if self.last_verified is None:
            return Fact(
                name=LAST_VERIFIED_FACT,
                source=Source.UNKNOWN,
                because=(
                    "no restore has ever been verified on this install, so no copy held here "
                    "has been read back and checked. The backup dates above say the thing "
                    "that takes copies ran, and nothing else"
                ),
            )
        if self.latest_attempt is not None and not self.latest_attempt.verified:
            because = (
                "a rehearsal since this date restored a copy and the copy failed at least one "
                "check, so this is when a restore last worked rather than a statement about "
                "the copies held now"
            )
        else:
            because = (
                "measured by a rehearsal that restored a copy into a scratch target and asked "
                "it every required check, including whether it still refuses what it should "
                "refuse"
            )
        return Fact(
            name=LAST_VERIFIED_FACT,
            source=Source.MEASURED,
            value=self.last_verified.attempted_at.isoformat(),
            because=because,
        )

    @property
    def measured_rto_seconds(self) -> float | None:
        """How long the last verified restore took, or `None` when none has verified.

        Read off the verification rather than stored, so it cannot be present on a panel whose
        verified field is empty. `brain.ops.recovery.Verification` refuses a recovery time on a
        drill that recovered nothing, which is where that rule lives.
        """
        if self.last_verified is None:
            return None
        return self.last_verified.rto_seconds


def panel(
    *,
    backups: Sequence[Backup],
    verifications: Sequence[Verification],
    profile: str,
    now: datetime,
    unreadable: Sequence[Unreadable] = (),
    schedule: Sequence[Scheduled] = SCHEDULE,
    objectives: Sequence[RecoveryObjective] | None = None,
) -> Panel:
    """The panel M27.6.2 asks for: the copies, the last verified restore, and the rehearsal.

    `unreadable` is both halves of the bucket together: what `read_manifests` could not read
    and what `read_drills` could not read. One parameter rather than two, because the answer
    is the same for either and a caller passing only the first would produce a panel that is
    confident about rehearsals and cautious about copies, which is the wrong way round.

    Nothing here is defaulted to an empty sequence except `unreadable`, and that asymmetry is
    deliberate. An install with no copies and no rehearsals is the state this product is in,
    so making it the default would mean a caller that forgot to pass anything gets the honest
    alarming answer rather than a silent pass; but `backups` and `verifications` are what the
    panel is about, and a caller that has not read the bucket has not measured anything. A
    bucket with nothing unreadable in it is the ordinary case and says so by being empty.
    """
    objective = recovery_objective(profile, objectives)
    copies = copy_states(
        backups, profile=profile, now=now, schedule=schedule, objectives=objectives
    )
    verified = last_verified_restore(verifications)
    return Panel(
        profile=profile,
        copies=copies,
        last_verified=verified,
        latest_attempt=last_attempt(verifications),
        assurance=assurance_of(
            copies, verifications, objective=objective, now=now, unreadable=unreadable
        ),
        drill_is_due=drill_due(
            last_verified_at=None if verified is None else verified.attempted_at, now=now
        ),
        unreadable=tuple(unreadable),
    )
