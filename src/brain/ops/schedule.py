"""Which controls are owed a run right now, and which of them this process may start.

`brain.ops.controls` is the registry of mechanisms that have to keep running and the check
that says whether anything runs them. On 2026-09-09 the answer was eleven of thirteen: no
caller of any kind. This module is the other half of that finding, and item 47 in
`docs/needs-rupash.md` is the decision behind it: a small scheduler inside the application
container, rather than more timers in an account we hold or a runbook every client copies by
hand.

**The policy is here and the clock, the lock and the queue are not.** Nothing in this module
reads the time, opens a connection or starts anything. It is handed the registry, a record of
when each control last ran and an instant, and it answers which are owed. That is the split
`brain.ops.limits` and `brain.ops.limit_store` already make, for the reason CLAUDE.md gives:
the case that is always wrong is the boundary, and a boundary cannot be tested through a
module that opens a socket. `brain.ops.schedule_runner` is the half that holds the connection.

**A scheduler that runs a control something else already runs is worse than no scheduler.**
The audit anchor is reached by a GitHub Actions timer calling an HTTP route, and it is the one
control that works. Adding a second caller inside the process would give it two, running at
different cadences, both publishing a seal, and the failure would look like a working system
producing more anchors than it should. So the entry condition is not "is it due" but "is it
due *and* is this process the thing that starts it", and the registry already records the
second half. See `A_CONTROL_SOMETHING_ELSE_STARTS_IS_NOT_THIS_SCHEDULERS_TO_START`.

**The retention sweep deletes, and its first run on a real install deletes everything that
accumulated before the schedule existed.** That is not a bug, it is the mechanism doing its
job against a backlog nobody has looked at, and the difference between those two readings is
visible only to a person. So a control named in `DESTRUCTIVE` is scheduled in report-only mode
until its name appears in `released`, which is a value the installation carries rather than a
constant here. A release is a decision somebody made after reading a report, and this module
cannot make it. See
`A_SWEEP_RELEASED_BEFORE_ANYBODY_READ_ITS_REPORT_IS_A_DELETION_NOBODY_APPROVED`.

**A control that has never run is owed now and is not overdue.** The two are different
sentences and folding them together makes every control on a fresh install alert as decades
late on its first tick, which is a page full of red on day one and an operator who stops
reading it in a week. `Owed.late_by` is zero for a control with no recorded run, and
`Owed.first_run` says which case it is, so an alerting rule can tell "this has never run" from
"this stopped running" without subtracting dates. That distinction is the one
`brain.ops.controls.NOTHING_CALLS_IT_IS_NOT_THE_SAME_ALERT_AS_IT_IS_LATE` already argues for
at the registry level, and this is the same argument one layer down.

Rejected: reading the cadence from a configuration file so an operator could tune it without a
release. Every cadence in the registry is imported from the module that owns the mechanism and
carries a written argument for its number, and a file that could override it would make the
argument advisory. An install that needs a different cadence has a reason, and the reason
belongs beside the mechanism.

Rejected: skipping a control whose previous run is still going. It reads as obvious and it
hides the case that matters, which is a control that never finishes: skipped silently for ever
while every screen says it is scheduled. Overlap is prevented by the lock in the runner, which
fails to acquire and says so, and a control that cannot acquire its own lock twice running is
a finding rather than a skip.

**Two leaves were closed before anything could run a control, and this is what they need.**
`M28.2.4` asks for a scheduled production canary run with alerting and `M37.5.1.2` for a CI
assertion that each control appears in the scheduler. Both were claimed against
`brain.ops.controls`, which lists the controls and checks the list against the source, and at
the moment they were claimed there was no scheduler for a control to appear in. Naming them
here rather than closing them again, because the registry half is genuinely done and the
running half is this.

Task ids: M28.2.4, M37.5.1.2
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.ops.controls import CONTROLS, Control, Invocation

#: How often the runner asks this module what is owed.
#:
#: Thirty seconds, and the figure is derived rather than chosen: the shortest cadence in the
#: registry is one minute (`queue_redrive`, `side_effect_resume`, `model_health_probes`), and
#: a tick at the cadence itself means a control is started every *other* tick whenever the two
#: drift by a second, which halves its real frequency with nothing reporting a miss. Half the
#: shortest cadence is the coarsest tick that cannot do that: a control is then late by at
#: most one tick rather than by a whole interval. `scheduling_gaps` is the check that keeps it
#: true when somebody adds a faster control, and it is a finding rather than a refusal because
#: the fix is to move this number, which is a decision with its own argument.
TICK: Final = timedelta(seconds=30)

#: Controls that remove data when they run, by name.
#:
#: One today. The set exists rather than a flag on the control because the registry describes
#: what a mechanism guards and not what it costs to run, and adding "does this delete" to
#: every row would put the question in thirteen places to be answered wrong in one.
DESTRUCTIVE: Final[frozenset[str]] = frozenset({"retention_sweep"})

#: Why a destructive control does not simply start running once a schedule exists.
A_SWEEP_RELEASED_BEFORE_ANYBODY_READ_ITS_REPORT_IS_A_DELETION_NOBODY_APPROVED: Final = (
    "The retention sweep deletes everything past its window. Its first run on an install "
    "that has been accumulating rows since setup removes all of it at once, which is the "
    "mechanism working and is indistinguishable, from the inside, from the mechanism being "
    "misconfigured. Nothing in this process can tell those apart, so it runs in report-only "
    "mode until somebody names it in the installation's released set, which is a record that "
    "a person read a report and decided."
)

#: Why being due is not enough on its own.
A_CONTROL_SOMETHING_ELSE_STARTS_IS_NOT_THIS_SCHEDULERS_TO_START: Final = (
    "The audit anchor is called by a timer outside this process and it is the one control "
    "that has always worked. A scheduler that started it as well would give it two callers "
    "at two cadences, and the symptom is a system publishing more seals than its schedule "
    "says, which reads as working. A control is this scheduler's only while the registry "
    "records that nothing else starts it."
)

#: Why a control that has never run is not reported as overdue.
A_CONTROL_THAT_HAS_NEVER_RUN_IS_OWED_AND_IS_NOT_LATE: Final = (
    "Subtracting a missing date from now makes every control on a fresh install decades "
    "overdue on the first tick. An operator who opens a new system to thirteen critical "
    "alerts learns within a week that the whole category is noise, which is the outcome this "
    "scheduler exists to avoid."
)

#: Why a run recorded in the future is refused rather than ignored.
A_RUN_RECORDED_IN_THE_FUTURE_IS_A_CLOCK_THAT_MOVED: Final = (
    "A last-run timestamp after the current instant did not happen. Treating it as recent "
    "silences the control until the clock catches up, which on a host that stepped back an "
    "hour is an hour of a safety mechanism not running and nothing saying so. Treating it as "
    "due runs a sweep twice. Neither is a decision this module may take quietly, so it is a "
    "finding."
)


class ScheduleError(Exception):
    """Raised when a schedule is described in a way nothing can act on."""


@dataclass(frozen=True)
class Owed:
    """One control the scheduler intends to start, and everything a reader needs about why.

    `late_by` is the gap beyond the cadence rather than the gap since the last run, so a
    control that is exactly on time is late by nothing and the number can be compared against
    `Control.alert_after` without re-deriving the cadence.

    `first_run` and a `late_by` of zero are not the same statement and both are kept. A
    control that has never run is owed immediately and is not late; one that ran on time is
    also not late. Only the first is worth telling somebody about on a fresh install. See
    `A_CONTROL_THAT_HAS_NEVER_RUN_IS_OWED_AND_IS_NOT_LATE`.
    """

    #: The control's name in the registry.
    name: str
    #: The instant it became owed: the last run plus the cadence, or `now` for a first run.
    due_since: datetime
    #: How far beyond its cadence it is, zero when it is on time or has never run.
    late_by: timedelta
    #: True when nothing has ever recorded a run of this control.
    first_run: bool
    #: True when this run may only report what it would do. See `DESTRUCTIVE`.
    report_only: bool

    def __post_init__(self) -> None:
        if self.late_by < timedelta(0):
            msg = f"{self.name!r} is late by {self.late_by}, which is a control owed in the past"
            raise ScheduleError(msg)
        if self.first_run and self.late_by:
            msg = (
                f"{self.name!r} has never run and is reported {self.late_by} late. "
                f"{A_CONTROL_THAT_HAS_NEVER_RUN_IS_OWED_AND_IS_NOT_LATE}"
            )
            raise ScheduleError(msg)


def schedulable(controls: Sequence[Control] | None = None) -> tuple[Control, ...]:
    """The controls this process is the one to start, in registry order.

    Everything the registry records as started from outside is excluded, which today is the
    audit anchor. See `A_CONTROL_SOMETHING_ELSE_STARTS_IS_NOT_THIS_SCHEDULERS_TO_START`.

    `IN_PROCESS` is included rather than excluded, and the distinction is worth stating: a
    control another module calls is not thereby running on a cadence. `spend_correction` is
    called by the cost review section of the usage screen, which runs when somebody opens it,
    so its caller is a screen and not a schedule. `brain.ops.controls.chains_worth_checking`
    makes the same point about the same control.
    """
    return tuple(
        one
        for one in (CONTROLS if controls is None else controls)
        if one.invoked_by is not Invocation.ON_A_ROUTE
    )


def owed(
    *,
    now: datetime,
    last_run: Mapping[str, datetime],
    controls: Sequence[Control] | None = None,
    released: Collection[str] = (),
) -> tuple[Owed, ...]:
    """Every control due a run at `now`, in registry order.

    `last_run` holds the instant each control last completed; a control missing from it has
    never run and is owed immediately. `released` names the destructive controls somebody has
    approved for real runs, and anything in `DESTRUCTIVE` outside it is returned with
    `report_only` set rather than withheld: a sweep that is silently not scheduled is the
    defect this whole module exists for.

    Takes its inputs rather than reading the registry and a clock, for the reason
    `brain.ops.starter.starter_gaps` records: a decision that can only be run against the real
    tree at the real instant cannot be shown to refuse anything, and both of its refusals
    survived a mutation run when it was written that way.
    """
    found: list[Owed] = []
    for one in schedulable(controls):
        previous = last_run.get(one.name)
        if previous is None:
            found.append(
                Owed(
                    name=one.name,
                    due_since=now,
                    late_by=timedelta(0),
                    first_run=True,
                    report_only=one.name in DESTRUCTIVE and one.name not in released,
                )
            )
            continue
        # No guard here for a run recorded after `now`, and its absence is the finding rather
        # than the omission. `Control.every` is refused at or below zero, so a previous run in
        # the future puts `due_at` in the future too and the next line already declines it. A
        # guard that cannot fire is this repository's most common defect and writing one that
        # reads as a clock-skew check would have made the skew look handled here. It is
        # handled in `scheduling_gaps`, where a person reads it.
        due_at = previous + one.every
        if due_at > now:
            continue
        found.append(
            Owed(
                name=one.name,
                due_since=due_at,
                late_by=now - due_at,
                first_run=False,
                report_only=one.name in DESTRUCTIVE and one.name not in released,
            )
        )
    return tuple(found)


def scheduling_gaps(
    *,
    now: datetime,
    last_run: Mapping[str, datetime],
    controls: Sequence[Control] | None = None,
    tick: timedelta = TICK,
) -> tuple[str, ...]:
    """Everything about this schedule that would make it report a run that did not happen.

    Three findings, and none of them is visible from a control being due.

    A run recorded after `now` is a clock that stepped rather than a run that happened, and
    the two readings of it are silence and a double run, so it is neither.
    See `A_RUN_RECORDED_IN_THE_FUTURE_IS_A_CLOCK_THAT_MOVED`.

    A cadence at or below twice the tick cannot be met: the control is started on some ticks
    and not others depending on where the two land, and its real frequency is whatever the
    drift makes it. Reported rather than raised, because the fix is to move `TICK`, which is a
    decision with its own argument beside it.

    A name in `DESTRUCTIVE` that the registry does not contain is an exemption that has
    outlived the thing it exempted, and a stale exemption is one waiting to cover the next
    control that happens to take the name. `brain.ops.controls.NOT_A_SCHEDULE` refuses its own
    entries for the same reason.
    """
    found: list[str] = []
    every = schedulable(controls)
    for one in every:
        previous = last_run.get(one.name)
        if previous is not None and previous > now:
            found.append(
                f"{one.name!r} last ran at {previous.isoformat()}, which is after "
                f"{now.isoformat()}. "
                f"{A_RUN_RECORDED_IN_THE_FUTURE_IS_A_CLOCK_THAT_MOVED}"
            )
        if one.every < tick * 2:
            found.append(
                f"{one.name!r} runs every {one.every} and the scheduler ticks every {tick}, so "
                "it is started on some ticks and not others and its real cadence is the drift"
            )
    known = {one.name for one in every}
    for name in sorted(DESTRUCTIVE - known):
        found.append(
            f"{name!r} is named as destructive and this scheduler has no such control, so the "
            "protection is on a name rather than on a mechanism"
        )
    return tuple(found)


def report_only_now(released: Collection[str] = ()) -> tuple[str, ...]:
    """The destructive controls that will report rather than act, in name order.

    Separate from `owed` so a console can answer "what is switched on" without asking what is
    due at this instant, which is a question whose answer changes every minute and would make
    a screen that flickers.
    """
    return tuple(sorted(DESTRUCTIVE - set(released)))
