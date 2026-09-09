"""The half of the scheduler that holds a connection, and what each control still needs.

`brain.ops.schedule` decides what is owed and reads no clock, opens no connection and starts
nothing. This is the other half: the lock that stops two replicas running one control, the two
queries that answer when each control last ran and last succeeded, and the loop that ticks.

**Two clocks, and reading one of them twice is the failure this is built around.** When a
control may next be *tried* is measured from its last attempt, so a control that fails does
not run again thirty seconds later and then two thousand eight hundred and eighty times a day.
How *late* it is, is measured from its last **success**, because a mechanism that has been
failing hourly for a week has not run for a week. Fold the two into one column and you get a
control that is permanently on time and permanently broken, which is precisely the shape
`brain.ops.controls` was written about. See `TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS`.

**`pg_advisory_xact_lock`, not `pg_advisory_lock`, and it is not a preference.** The
application talks to PgBouncer in transaction mode, where consecutive statements from one
client can land on different server connections, so a session-level lock is taken on one
connection while every later statement runs somewhere else: mutual exclusion is gone and
nothing says so. `brain.migrate` learned this the expensive way and its comment is the record.
Transaction-scoped, and it is released when the transaction ends however it ends.

**Try, do not wait.** `brain.migrate` blocks, because a replica that loses the migration race
must not serve against an unmigrated schema. Here the opposite is right: a replica that cannot
take a control's lock means another replica is running that control, and waiting would hold a
connection open for the length of a sweep to then discover there is nothing to do. It moves on
and the control is picked up on a later tick by whoever is free. See
`A_LOCK_THIS_CANNOT_TAKE_MEANS_SOMEBODY_ELSE_IS_RUNNING_IT`.

**A lock per control, not one for the scheduler.** One lock would serialise thirteen unrelated
mechanisms behind whichever is slowest, and a retention sweep is the slowest thing here. The
identifier is derived from the control's name so it cannot be typed wrong and cannot collide
with `brain.migrate`'s.

**Nothing is wired yet and that is stated rather than implied.** Every one of the twelve
control entry points is a policy function that takes its inputs: `retention.enforcement_report`
takes a census "the executor saw", `denial_alerts.digest` takes patterns and recipients,
`recovery.alerts` takes backups and verifications. None of them gathers anything. So the
registry's eleven orphans are not eleven mechanisms waiting for a timer, they are eleven
mechanisms whose policy is written and whose input gathering does not exist, and a scheduler
alone does not switch them on. `runner_gaps` reports each one by name, which turns "eleven
mechanisms nothing runs" into a list of named pieces of work. See
`A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT`.

**A runner has to call its control in a way `brain.ops.controls` can see.** That registry
reads `ast.Call` nodes to answer "does anything call this", and its own docstring says it
cannot resolve a callable passed as an argument or anything dynamic. So a dispatch table of
function references would run the controls while the registry went on reporting that nothing
calls them, which is the same lie one layer down. Each runner is therefore a function in this
module making a literal call, and `RUNNERS` maps a name to one of those.

Rejected: a thread. The application is async and a thread would need its own engine, its own
session scope and its own error handling, and the two would drift. The loop is a task on the
running event loop, cancelled when the application stops.

Rejected: recording a run before taking the lock, so that a contended tick leaves a trace. It
would fill the table with rows for runs that never happened, and "this control has thousands
of attempts and no successes" would then mean two different things.

Task ids: M37.5.1.3
"""

from __future__ import annotations

import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from brain.ops.controls import Control
from brain.ops.schedule import TICK, Owed, owed, schedulable

#: Why the two questions are two columns.
TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS: Final = (
    "A control that fails every attempt has run recently and has not worked for however long "
    "it has been failing. Measuring dueness from the last attempt is what stops a broken "
    "control being retried on every tick; measuring lateness from the last success is what "
    "stops it reporting as healthy. One column cannot say both, and the version that says "
    "only the first is a mechanism that is permanently on time and permanently broken."
)

#: Why a lock that cannot be taken is not an error.
A_LOCK_THIS_CANNOT_TAKE_MEANS_SOMEBODY_ELSE_IS_RUNNING_IT: Final = (
    "Two replicas tick at the same time and both find the same control owed. The one that "
    "cannot take the lock has learned that the other is running it, which is the system "
    "working. Waiting would hold a connection for the length of a sweep to discover there is "
    "nothing to do, and treating it as a failure would record an attempt that never happened."
)

#: Why the module ships with an empty dispatch table and says so.
A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT: Final = (
    "Every control entry point in the registry is a policy function taking its inputs, and "
    "nothing in this system gathers those inputs. Wiring a control means writing its "
    "gatherer, one at a time, each with its own tests. A dispatch table filled with calls "
    "that pass empty sequences would make every control report a successful run having "
    "examined nothing, which is worse than the state it replaced: the console would say the "
    "estate is protected and a run record would agree with it."
)

#: The advisory lock namespace, so a control's lock cannot collide with `brain.migrate`'s.
#:
#: PostgreSQL's two-argument advisory lock takes a pair of 32-bit integers, and using the pair
#: rather than one 64-bit value is what makes the namespace visible in `pg_locks` instead of
#: being hidden inside an arithmetic combination somebody would have to reverse.
SCHEDULER_LOCK_NAMESPACE: Final = 0x5C4E

#: How long a run may hold its lock before the scheduler stops waiting for it to finish.
#:
#: Ten minutes, against a shortest cadence of one minute. Not a timeout on the control, which
#: this cannot enforce without killing work halfway: it is how long a row may sit with a
#: `started_at` and no `finished_at` before `stalled_runs` calls it stalled. A control that
#: legitimately takes longer than this needs its own figure beside it and an argument for it.
STALLED_AFTER: Final = timedelta(minutes=10)


class RunnerError(Exception):
    """Raised when a schedule is asked to run something it cannot describe."""


@dataclass(frozen=True)
class Runner:
    """One control this process knows how to start, and what it needs to do it.

    `run` makes a literal call to the control's entry point, in this module, so
    `brain.ops.controls` can see it. A reference stored here and called through a variable
    would run the control while the registry went on reporting that nothing calls it.

    `needs` is the sentence naming what still has to exist before the control can be wired,
    and it is empty exactly when `run` is set. Keeping the two in one type is what makes
    `runner_gaps` a list of named work rather than a count.
    """

    #: The control's name in `brain.ops.controls.CONTROLS`.
    name: str
    #: What still has to be built before this can run, empty when it can.
    needs: str = ""
    #: The call, when there is one.
    run: Callable[[datetime, bool], str] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a runner with no control name cannot be dispatched to or reported on"
            raise RunnerError(msg)
        if self.run is None and not self.needs.strip():
            msg = (
                f"{self.name!r} has nothing to run and does not say what it needs, so it is "
                "indistinguishable from a control somebody forgot. "
                f"{A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT}"
            )
            raise RunnerError(msg)
        if self.run is not None and self.needs.strip():
            msg = (
                f"{self.name!r} can be run and also says what it still needs, which reads as "
                "a control that is wired and is not"
            )
            raise RunnerError(msg)


#: What each schedulable control still needs before it can be started, by name.
#:
#: Twelve entries and no `run` among them, which is the honest state on 2026-09-09 and is the
#: point of the module header. Each sentence is a piece of work somebody can pick up, written
#: from reading the entry point's own signature rather than from a guess about it.
RUNNERS: Final[tuple[Runner, ...]] = (
    Runner(
        name="retention_sweep",
        needs=(
            "an executor that walks every store in `brain.ops.retention.Store` and produces "
            "the `StoreCensus` sequence `enforcement_report` takes. The report is written and "
            "correct and there is nothing that counts what is actually in each store"
        ),
    ),
    Runner(
        name="canary_run",
        needs=(
            "the two askers `compare_askers` compares, as live entitlement sets, and the "
            "store scan it compares them over. Both are arguments today and nothing builds "
            "either"
        ),
    ),
    Runner(
        name="restore_drill",
        needs=(
            "somewhere a drill's result is recorded. `drill_due` takes the last verification "
            "and `verification_of` reads one, and no backup or verification is written by "
            "anything: Needs Rupash item 44 is that work and its option C was chosen"
        ),
    ),
    Runner(
        name="backup_exposure",
        needs=(
            "the backup and verification sequences `alerts` takes, which are the same rows "
            "item 44's nightly dump would produce"
        ),
    ),
    Runner(
        name="denial_digest",
        needs=(
            "the denial patterns of the window and the recipients to send to. The patterns "
            "come from the audit ledger and nothing queries it for them; the recipients are "
            "entitlement sets and nothing resolves the set of people who should receive a "
            "digest"
        ),
    ),
    Runner(
        name="directory_sync",
        needs=(
            "a roster source. `is_due` and `dry_run` are the policy and the source interface "
            "is M1.6.1, whose implementation is chosen per client: Needs Rupash item 39 "
            "settles that every source stays selectable at deploy time"
        ),
    ),
    Runner(
        name="knowledge_reverification",
        needs=(
            "a query for the items whose `review_by` has passed. "
            "`open_reverification_tasks` turns those items into tasks and nothing finds them"
        ),
    ),
    Runner(
        name="resolution_calibration",
        needs=(
            "the feature observations `drift` measures over. The fit is weekly and the "
            "observations are resolution decisions nobody records for this purpose yet"
        ),
    ),
    Runner(
        name="queue_redrive",
        needs=(
            "a queue. `verdict_for` decides what to do with a stuck job and `redrive` acts on "
            "the verdict; no queue driver is installed, which is why both workers exit at "
            "startup today"
        ),
    ),
    Runner(
        name="side_effect_resume",
        needs=(
            "the same queue, plus the idempotency records `resume` reads. A side effect "
            "cannot be resumed before there is a queue that could have interrupted one"
        ),
    ),
    Runner(
        name="model_health_probes",
        needs=(
            "an inference endpoint to probe and somewhere to put the result. `next_probes` "
            "says which deployments are due a probe; issuing one needs the client and the "
            "inference server, which Needs Rupash items 25 and 31 are about"
        ),
    ),
    Runner(
        name="spend_correction",
        needs=(
            "nothing new, and it is the closest to wireable. `correct` already has a caller "
            "in `brain.console.spend_view`, so what it needs is the estimate and actual "
            "figures for the period, which the usage screen assembles when somebody opens it "
            "and nothing assembles on a schedule"
        ),
    ),
)


def runner_for(name: str, runners: Sequence[Runner] = RUNNERS) -> Runner:
    """One runner by name, refusing an unknown one rather than answering None.

    Refuses for the reason `brain.deployment.installer.step_named` refuses: a caller handed
    None writes `if runner is None: return` and the control silently stops being scheduled,
    which is the failure this whole area exists to report.
    """
    for one in runners:
        if one.name == name:
            return one
    msg = f"no runner named {name!r}; the schedulable controls are {[r.name for r in runners]}"
    raise RunnerError(msg)


def runner_gaps(
    controls: Sequence[Control] | None = None, runners: Sequence[Runner] = RUNNERS
) -> tuple[str, ...]:
    """Every schedulable control this process cannot actually start, and what each needs.

    A report rather than a gate, in the shape `brain.ops.controls.orphans` takes and for the
    same reason: twelve of twelve are unwired today and a check asserting otherwise would be
    red on arrival and switched off within the week. What is a gate is the pair of
    disagreements below, which are green today and go red the moment the two lists drift.

    Reported in registry order rather than sorted, so the output reads in the same order as
    `handover_lines` and the two can be put beside each other.
    """
    every = schedulable(controls)
    known = {one.name for one in runners}
    found: list[str] = []

    for one in every:
        if one.name not in known:
            found.append(
                f"{one.name!r} is scheduled by this process and has no runner at all, so it "
                "would be found owed on every tick and started by nothing"
            )
            continue
        runner = runner_for(one.name, runners)
        if runner.run is None:
            found.append(f"{one.name!r} cannot be started yet: it needs {runner.needs}")

    for name in sorted(known - {one.name for one in every}):
        found.append(
            f"{name!r} has a runner and is not a control this process schedules, so the "
            "runner is either dead or the registry has moved it onto an external timer"
        )
    return tuple(found)


def lock_id(name: str) -> tuple[int, int]:
    """The advisory lock a control takes, as PostgreSQL's pair of 32-bit integers.

    Derived from the name with CRC32 rather than from a hand-kept table of numbers, because a
    table of numbers is a second place a control exists and the failure of a duplicate is two
    unrelated mechanisms silently serialising behind one lock.

    CRC32 rather than a cryptographic digest: this needs a stable 32-bit integer and nothing
    about it is a security property, and `hash()` is salted per process, which would give two
    replicas two different locks for one control. That is the bug this function exists to
    make impossible, so it is worth saying out loud.
    """
    if not name.strip():
        msg = "an unnamed control has no lock, and every caller of this would share one"
        raise RunnerError(msg)
    # Signed, because PostgreSQL's advisory lock arguments are signed 32-bit integers and a
    # value above 2^31 is refused rather than wrapped.
    unsigned = zlib.crc32(name.encode("utf-8"))
    return SCHEDULER_LOCK_NAMESPACE, unsigned - (1 << 32) if unsigned >= (1 << 31) else unsigned


def due_now(
    *,
    now: datetime,
    last_attempt: Mapping[str, datetime],
    last_success: Mapping[str, datetime],
    controls: Sequence[Control] | None = None,
    released: Sequence[str] = (),
) -> tuple[Owed, ...]:
    """What is owed at `now`, with dueness on one clock and lateness on the other.

    `owed` is asked twice rather than given both maps, and that is deliberate: the policy
    module has one notion of a last run and giving it two would put this module's argument
    about failures inside a module that must not know what an outcome is. The dueness answer
    decides *what* is returned; the lateness answer supplies `late_by` and `first_run` for the
    ones that survived. See `TRIED_RECENTLY_AND_WORKING_ARE_DIFFERENT_CLOCKS`.
    """
    trying = owed(now=now, last_run=last_attempt, controls=controls, released=released)
    by_success = {
        one.name: one
        for one in owed(now=now, last_run=last_success, controls=controls, released=released)
    }
    # `report_only` is taken from this run's answer, and a mutation says the choice does not
    # matter today: `owed` computes it from the control's name and the released set, neither
    # of which depends on the instant or on the map it was given, so both answers agree for
    # every input. Recorded rather than tested around, because the equivalence is a property
    # of `owed` rather than of this line, and it would stop holding the day a release became
    # something with a date on it.
    return tuple(
        Owed(
            name=one.name,
            due_since=one.due_since,
            late_by=by_success[one.name].late_by if one.name in by_success else one.late_by,
            first_run=by_success[one.name].first_run if one.name in by_success else one.first_run,
            report_only=one.report_only,
        )
        for one in trying
    )


def stalled_runs(
    started: Mapping[str, datetime], *, now: datetime, after: timedelta = STALLED_AFTER
) -> tuple[str, ...]:
    """Controls whose newest run began and never recorded finishing, in name order.

    A row with a `started_at` and no `finished_at` is either a run still going or a process
    that died holding it. This does not distinguish them and does not pretend to: the lock
    does, because a dead process released its transaction and a live one has not. What this
    answers is which rows are old enough to be worth asking about, so a console can show the
    question rather than a number nobody can interpret.
    """
    if after <= timedelta(0):
        msg = f"a run is stalled after {after}, which is every run the moment it starts"
        raise RunnerError(msg)
    return tuple(sorted(name for name, at in started.items() if now - at > after))


def next_tick(*, now: datetime, tick: timedelta = TICK) -> datetime:
    """When the loop should wake next.

    Aligned to the tick rather than added to the current instant, so a tick that took four
    seconds does not push every later tick four seconds further out. Drift accumulated that
    way is what makes a one-minute control run every seventy seconds by the end of a day, and
    nothing reports it because every individual tick was on time.
    """
    if tick <= timedelta(0):
        msg = f"a tick of {tick} would wake the loop continuously"
        raise RunnerError(msg)
    since = (now - datetime.min.replace(tzinfo=UTC)) % tick
    return now + (tick - since)
