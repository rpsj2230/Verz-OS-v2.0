"""Every mechanism that has to keep running, what it guards, and whether anything runs it.

**A safety mechanism with no caller is worse than no safety mechanism, because the console
says the estate is protected.** That is the defect this file exists for, and it is invisible
to every gate this repository has: mypy passes, the tests pass, the sweeps pass, and the
retention window silently never prunes. `brain.ops.worker` names it as the most common defect
here and `brain.ops.jobs` says the same about itself; both were written by somebody who found
it in their own module. Saying so in a docstring is what those two could do. This is the
check.

**The registry is derived where it can be and asserted where it cannot, and the split is
stated rather than blurred.** What is derived, by reading the source: whether each named
function exists, who calls it, whether some module declares the HTTP route a control names
and whether that same module is one of the callers, whether a declared workflow file carries
a schedule and names that route, and whether any recurrence predicate in the tree is missing
from this list. What is asserted: which functions belong to one control, what that control
guards, and where its cadence came from. A registry that is entirely hand-typed
is a second thing to keep in sync and its failure mode is precisely that it drifts and goes
on saying everything is fine, so the hand-typed part is confined to the sentence a machine
cannot write.

**The cadence is imported, never retyped.** `CANARY_INTERVAL_SECONDS`, `DIGEST_WINDOW`,
`DRILL_INTERVAL_DAYS`, `SYNC_INTERVAL`, `DEFAULT_CADENCE`, `CALIBRATION_PERIOD` and
`PROBE_INTERVAL_SECONDS` are each declared beside the mechanism they belong to, with an
argument for the number. Copying any of them here would produce two numbers, and the one that
gets tuned is the one next to the code while the one that gets alerted on is this one. Where
the figure came from is recorded on the row as `cadence_from` and checked, so the four
mechanisms whose own module declares no interval say so rather than looking the same as the
nine that do: a mechanism that has to run and has nothing saying how often is a finding in
its own right, and `advisories` is where it is said out loud.

**`invoked_by` is a claim about the source that the source is asked about.** Declaring it as
data rather than computing it everywhere is what makes the regression catchable: a control
that has a caller today and loses it tomorrow fails `registry_gaps` immediately, whereas a
purely computed answer would simply return a different number and nothing would know it had
been higher. It also means the honest state of the estate is written down in one readable
place rather than being a count somebody has to go and produce.

**Nothing here is red on arrival, and that is deliberate rather than a dodge.**
`brain.ops.sweeps.sweep_house_style` records the argument at length: a check that goes red the
day it lands is a check somebody switches off. Twelve of the thirteen controls below have no
caller of any kind, and a gate asserting that they do would be switched off within the week.
What is asserted instead is that the registry and the source agree, in both directions, which
is green today and goes red the moment a control is wired without being recorded, a control is
recorded as wired when it is not, or a control that was wired stops being. The orphan count is
not hidden by that: `orphans` returns them, `handover_lines` prints the state of each one into
the pack a client is handed, and the invariant test asserts the set rather than a number.

**The one control that runs is not driven from Python.** `audit_anchor` is reached by a
GitHub Actions cron calling an HTTP route, which is why `Invocation` has a member for it. A
model that could only express "another module calls this function" would have reported the
one working control as an orphan, and a check that is wrong about the working case is a check
nobody believes about the broken ones.

Rejected: discovering the control set from the code rather than listing it. There is no shape
in this repository that separates a mechanism which must run from a function that happens to
be periodic, and inventing one, a decorator say, would mean editing nine modules to add a
marker that means whatever the last person to add it thought. What is discovered instead is
the *converse*: every module-level recurrence predicate in the tree must appear here, so the
list cannot silently fall behind the code even though it cannot be generated from it.

Rejected: a sweep of its own. `brain.ops.sweeps` is the right home for a check over the whole
codebase and this is one, but `tests/invariants` already runs in CI, already runs in the
pre-push hook, and is where a rule the system must never break is written down. A sweep would
have added a second place to look for the same answer.

Rejected: making `overdue` return a bool per control. Four things can be wrong and they send
a person to four different places: nothing calls it, nothing records it, it is recorded and
has never happened, or it happened and not recently enough. A bool answers the first three
identically and the answer it gives is "check the scheduler", which for a control nothing
calls is the one place with nothing to find.

Scope: domain logic, with one exception that is the point of the module, and the line between
the two halves matters on an installed system. Nothing here reads a clock, opens a connection
or runs anything; `now` and the last-run times are parameters. The exception is that the
derived checks read the repository from disk, exactly as `brain.ops.sweeps` and
`brain.ops.install_from_empty` do, because what they assert is about the source rather than
about a value. **Everything an installed system would call is on the pure side**: `orphans`,
`overdue`, `runbook_for`, `advisories` and `handover_lines` touch no file, so a container
built without its own source tree still alerts and still prints a handover pack. Only the
checks that exist for CI go to disk, and a deployment where `REPO` points at nothing is a
deployment where those were never going to be asked.

Task ids: M37.4.3.4, M37.5.1.1, M37.5.1.2, M37.5.1.3, M37.5.1.4
"""

from __future__ import annotations

import ast
import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from brain.identity.staff_sync import SYNC_INTERVAL
from brain.knowledge.verification import DEFAULT_CADENCE
from brain.models.health import PROBE_INTERVAL_SECONDS
from brain.ops.alerting import Runbook, Severity, route_for
from brain.ops.alerting import runbook_gaps as route_runbook_gaps
from brain.ops.canaries import CANARY_INTERVAL_SECONDS
from brain.ops.denial_alerts import DIGEST_WINDOW
from brain.ops.handover import Residue
from brain.ops.queue import stale_after
from brain.ops.recovery import DRILL_INTERVAL_DAYS
from brain.resolution.calibration import CALIBRATION_PERIOD

#: The repository this module was installed from, used only by the derived checks below.
#:
#: Four levels up from `src/brain/ops/controls.py`, exactly as `brain.ops.sweeps.REPO` is
#: derived and for the same reason: a path written out would be one more thing that is right
#: on the machine it was typed on.
REPO: Final[Path] = Path(__file__).resolve().parents[3]

#: Where the derived checks look for callers. Everything this repository ships as code.
SRC: Final[Path] = REPO / "src" / "brain"

# ------------------------------------------------------------------ written-down reasons
#: The sentence this whole module exists to make checkable.
A_MECHANISM_WITH_NO_CALLER_IS_WORSE_THAN_NO_MECHANISM: Final = (
    "A guard nothing runs is not a missing guard, it is a false one. The code is present, "
    "the tests are green, the module docstring explains what it protects, and every screen "
    "that reads the registry reports the estate as covered. The absence of the guard would "
    "at least be visible as an absence. So the question this module asks is not whether the "
    "mechanism is correct, which the unit tests answer, but whether anything at all calls "
    "it, which nothing else in this repository has ever asked."
)

#: Why the reachability answer is written down as data rather than only computed.
A_COMPUTED_ANSWER_CANNOT_NOTICE_THAT_IT_USED_TO_BE_DIFFERENT: Final = (
    "Computing who calls a control on every run gives the right answer and cannot tell you "
    "that the answer changed. A control wired up in March and quietly unwired in June "
    "produces a smaller number and no failure, because nothing recorded what the number was. "
    "Declaring it and checking the declaration against the source makes the regression the "
    "loud case: the day a caller disappears, the registry disagrees with the tree and the "
    "invariant fails, naming the control and the direction it moved in."
)

#: Why nothing calling a control is reported differently from a control being late.
NOTHING_CALLS_IT_IS_NOT_THE_SAME_ALERT_AS_IT_IS_LATE: Final = (
    "Both end with the mechanism not having run, and they send a person to opposite ends of "
    "the system. Late means the schedule exists and did not fire, so the answer is in the "
    "scheduler and somebody can start the thing by hand. Unreachable means there is no "
    "schedule and no call site, so the scheduler is exactly the place with nothing to find, "
    "and an hour spent there is an hour spent confirming that a thing which was never wired "
    "is not wired. One alert for both is the version that wastes the hour."
)

#: Why a control cannot be marked as running until every part of it is called.
A_CONTROL_IS_RUN_ONLY_WHEN_ALL_OF_IT_IS: Final = (
    "A control is usually several functions: one that says whether a run is owed and one or "
    "more that do the work. Counting the control as wired because any one of them has a "
    "caller is how a system ends up asking whether a canary sweep is due, every twelve "
    "hours, for ever, and never sweeping. The conservative direction is the correct one "
    "here, because the failure being looked for is a mechanism that reports itself healthy."
)


class ControlsError(Exception):
    """A control was declared in a shape the registry cannot check or an operator cannot read.

    Outside `brain.core.errors` for the reason `brain.ops.jobs.JobsError` gives about itself:
    nobody asking a question ever sees one of these. It is a mistake by whoever added a row.
    """


# --------------------------------------------------------------- how a control is reached
class Invocation(enum.StrEnum):
    """How a control is started today. Three members, and each one is a different search.

    That is the test for a member here rather than tidiness: two ways of being started that
    lead a reader to the same file are one member with two names.
    """

    #: Nothing calls it. Not a schedule that is misconfigured: no call site of any kind.
    NOTHING = "nothing"
    #: Another module in this repository calls it. Whether *that* module is itself reached is
    #: a separate question and this does not answer it; see `chains_worth_checking`.
    IN_PROCESS = "in_process"
    #: An HTTP route reaches it and something outside the process calls the route on a
    #: schedule. The route and the schedule are both checked, because either one alone is a
    #: mechanism that does not run.
    ON_A_ROUTE = "on_a_route"


#: The form every symbol in the registry takes: an importable module, then a function.
_SYMBOL_RE: Final = re.compile(r"^[a-z][a-z0-9_.]*[a-z0-9_]:[a-z_][a-z0-9_]*$")

#: The same, for a name that may be a constant. A separate pattern rather than a looser one
#: shared with the above, because a control naming an upper-case entry point is a mistake
#: worth refusing and a cadence naming a lower-case one is not.
_DECLARED_RE: Final = re.compile(r"^[a-z][a-z0-9_.]*[a-z0-9_]:[A-Za-z_][A-Za-z0-9_]*$")

#: What a recurrence predicate is called in this repository. `due`, or a name built from it.
#:
#: Every one of the six that exist follows it, and it is what makes the converse check
#: possible: a new predicate cannot be added without this registry refusing to describe the
#: control it belongs to. Deliberately narrow: a broad pattern over interval-shaped constants
#: matched session windows, cache lifetimes and retry backoffs, and a converse check with
#: false positives is one that gets an exclusion list, which is the thing being avoided.
_RECURRENCE_RE: Final = re.compile(r"^(due|due_.*|.*_due)$")


#: Recurrence-shaped names that are not schedules, each with the reason it is not one.
#:
#: The converse check found these on its first run and they are the case it has to be able to
#: express: `brain.ops.scaling` asks "is it time to partition this table", "is a read replica
#: warranted now", "is this report slow enough to materialise" and "has this install outgrown
#: its host". Every one reads as a recurrence predicate and none of them is: they are growth
#: triggers evaluated against a measurement, and they guard nothing. Registering them as
#: controls would put four rows in the handover pack claiming to protect an estate.
#:
#: A hand-written list, and the property that matters survives it: a new predicate still
#: cannot arrive without somebody deciding which of the two it is and writing the reason
#: down. What the list cannot do is rot quietly, because `registry_gaps` refuses an entry
#: naming a function that no longer exists: a stale exemption is an exemption waiting to
#: cover the next function that happens to take the same name.
NOT_A_SCHEDULE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "brain.ops.scaling:partitioning_is_due": (
            "a growth trigger asked of a retention window and a partition size, not a job. "
            "It guards nothing and running it on a timer would answer the same question "
            "every time until the window changes"
        ),
        "brain.ops.scaling:replica_is_due": (
            "a growth trigger asked of measured console reads against the answer path's "
            "headroom. Nothing is protected by asking it, and the answer is a capacity "
            "decision for a person"
        ),
        "brain.ops.scaling:report_is_due": (
            "a growth trigger asked of one report's observed latency. Materialising a view "
            "is a maintenance obligation taken on deliberately rather than a guarantee kept"
        ),
        "brain.ops.scaling:host_split_is_due": (
            "a growth trigger asked of the deployment profile against the measured host. It "
            "is the same arithmetic as the deployment check and is evaluated when somebody "
            "is deciding where to run this, not on a schedule"
        ),
    }
)


@dataclass(frozen=True)
class Control:
    """One mechanism that has to keep running, and the guarantee that stops holding if it
    does not.

    `symbols` rather than a single entry point, because a control is usually a predicate
    saying whether a run is owed plus the functions that do the work, and a control counted
    as running because one of the three has a caller is how a system asks whether a sweep is
    due for ever and never sweeps. See `A_CONTROL_IS_RUN_ONLY_WHEN_ALL_OF_IT_IS`.

    `guards` and `lost_silently` are the two hand-written sentences and they answer different
    questions. The first is what a client reads in the handover pack; the second is what an
    engineer reads at three in the morning, and it has to say why nothing else would have
    noticed, because if something else would have, this control is not the one to be looking
    at.
    """

    name: str
    #: Every function this control is, the first being the one a scheduler would call.
    symbols: tuple[str, ...]
    #: What it protects, in words a client can read. The asserted half of this registry.
    guards: str
    #: What stops being true when it stops running, and why nothing else reports it.
    lost_silently: str
    #: How often it has to run. Imported from the mechanism's own module wherever one
    #: declares an interval; see `cadence_is_declared_elsewhere` for the ones that do not.
    every: timedelta
    #: What being late costs, in `brain.ops.alerting`'s vocabulary rather than a word.
    severity: Severity
    #: Where the call comes from today. A claim, checked against the source by
    #: `registry_gaps`; see `A_COMPUTED_ANSWER_CANNOT_NOTICE_THAT_IT_USED_TO_BE_DIFFERENT`.
    invoked_by: Invocation
    #: Where `every` came from, as `module:name`, empty when nothing outside this registry
    #: declares it. Checked for existence by `registry_gaps`; see
    #: `cadence_is_declared_elsewhere` for why this is a name rather than a comparison.
    cadence_from: str = ""
    #: The HTTP path that reaches it, for a control started from outside the process.
    route: str = ""
    #: The file carrying the schedule, for a control whose recurrence is not in Python.
    schedule_file: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a control with no name cannot be alerted on, listed or handed over"
            raise ControlsError(msg)
        if not self.symbols:
            msg = (
                f"control {self.name!r} names no function, so there is nothing to ask "
                "whether anything calls, which is the only question this registry exists for"
            )
            raise ControlsError(msg)
        for symbol in self.symbols:
            if not _SYMBOL_RE.match(symbol):
                msg = (
                    f"control {self.name!r} names {symbol!r}, which is not module:function; "
                    "a symbol nothing can resolve is a row that passes every check by being "
                    "unaskable"
                )
                raise ControlsError(msg)
        if not self.guards.strip():
            msg = (
                f"control {self.name!r} does not say what it guards, and a registry of "
                "mechanisms nobody can explain is the list that gets disabled during an "
                "incident and never restored"
            )
            raise ControlsError(msg)
        if not self.lost_silently.strip():
            msg = (
                f"control {self.name!r} does not say what stops being true when it stops "
                "running, so nothing on its alert tells the reader why it matters"
            )
            raise ControlsError(msg)
        if self.every <= timedelta(0):
            msg = (
                f"control {self.name!r} runs every {self.every}, which is a cadence that is "
                "always owed, so it would be permanently overdue and permanently ignored"
            )
            raise ControlsError(msg)
        if self.cadence_from and not _DECLARED_RE.match(self.cadence_from):
            msg = (
                f"control {self.name!r} says its cadence comes from {self.cadence_from!r}, "
                "which is not module:name, so nothing can check that the name still exists "
                "and the provenance is a sentence rather than a claim"
            )
            raise ControlsError(msg)
        if self.invoked_by is Invocation.ON_A_ROUTE and not (self.route and self.schedule_file):
            msg = (
                f"control {self.name!r} says it is started from outside the process and "
                "names no route or no schedule file, so nothing can be checked and the claim "
                "rests on whoever wrote the row"
            )
            raise ControlsError(msg)

    @property
    def entry_point(self) -> str:
        """The function a scheduler would call. First rather than stored, so it cannot
        disagree with the list it is drawn from."""
        return self.symbols[0]

    @property
    def alert_after(self) -> timedelta:
        """How long past its cadence before being late is worth telling somebody about.

        Derived from the control's own interval rather than declared, so a mechanism whose
        cadence is tuned takes its alerting threshold with it. A control alerted at exactly
        its interval alerts on ordinary jitter: a twelve-hourly sweep that runs at 09:00 and
        then at 09:04 is a sweep that is working.
        """
        return self.every * MISSED_RUN_GRACE


#: How many whole intervals a control may miss before being late is worth saying.
#:
#: Two, so one missed run is silence and two consecutive misses is an alert. One missed run
#: is a deployment, a restart or a host that was busy; two in a row is the schedule being
#: gone, which is the thing worth a person. A value of one alerts on the jitter of a
#: mechanism that is working, which is how an operator learns to ignore the whole category,
#: and a value of three means a daily control is silent for most of a working week.
#:
#: Asserted against the property rather than against itself: a run exactly one interval old
#: is not late and a run at the threshold is, which is a statement about behaviour that
#: changing this number breaks.
MISSED_RUN_GRACE: Final = 2

#: How much longer than the acknowledgement window an unanswered alert waits before it
#: climbs. Two, for the reason `brain.ops.alerting.runbook_gaps` refuses anything at or below
#: one: escalating inside the time the first responder was given makes the rung above them
#: the first responder, and they stop reading their own alerts within a fortnight.
ESCALATE_AFTER_UNANSWERED: Final = 2


# ---------------------------------------------------------------------------- the registry
#: Cadences for mechanisms whose own module declares none. Named here so the omission is
#: visible rather than looking like a decision somebody made beside the code.
#:
#: Every other cadence in the registry is imported. These four are not, and
#: `cadence_is_declared_elsewhere` is how a reader tells the two apart without checking the
#: imports by hand.
_DAILY: Final = timedelta(days=1)
_WEEKLY: Final = timedelta(days=7)
_SIX_HOURLY: Final = timedelta(hours=6)

CONTROLS: Final[tuple[Control, ...]] = (
    Control(
        name="retention_sweep",
        symbols=("brain.ops.retention:enforcement_report", "brain.ops.retention:enforcement_gaps"),
        guards=(
            "that nothing is kept past the window its data class was given: traces, payloads, "
            "recordings, exports, backups and the metadata ledger each stop existing on the "
            "date the policy says they do"
        ),
        lost_silently=(
            "Nothing gets deleted and nothing reports that nothing got deleted. Every "
            "retention window in the console still reads correctly, because a window is a "
            "declaration rather than a measurement, and the first time anybody finds out is "
            "when a subject access request returns something that should have been gone."
        ),
        every=_DAILY,
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="canary_run",
        symbols=(
            "brain.ops.canaries:compare_askers",
            "brain.ops.canaries:scan_stores",
            "brain.ops.canaries:due",
        ),
        guards=(
            "that the gate still refuses what it refused yesterday, that a value one asker "
            "may not see never reaches a place a run leaves text behind, and that two "
            "refusals still read identically to the person receiving them"
        ),
        lost_silently=(
            "The central invariant stops being measured. Every other check in this "
            "repository asks whether the code is correct; this is the only one that asks "
            "whether the running system still behaves as the code says, and a change to who "
            "reaches what can break it without a single test failing."
        ),
        every=timedelta(seconds=CANARY_INTERVAL_SECONDS),
        cadence_from="brain.ops.canaries:CANARY_INTERVAL_SECONDS",
        severity=Severity.WOKEN,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="restore_drill",
        symbols=("brain.ops.recovery:drill_due", "brain.ops.recovery:verification_of"),
        guards=(
            "that the copies being taken can actually be restored, which is the only thing "
            "that turns a backup from a file into a recovery"
        ),
        lost_silently=(
            "Backups go on being written and go on appearing in every report as protection. "
            "Nothing about an unreadable copy is visible from the outside of it, so the "
            "estate reads as recoverable for exactly as long as nobody tries."
        ),
        every=timedelta(days=DRILL_INTERVAL_DAYS),
        cadence_from="brain.ops.recovery:DRILL_INTERVAL_DAYS",
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="backup_exposure",
        symbols=("brain.ops.recovery:alerts",),
        guards=(
            "that a stretch of work with no copy anywhere is noticed while it is still "
            "short, and that a rehearsal which ran and did not verify is treated as a "
            "statement about every copy held rather than about one of them"
        ),
        lost_silently=(
            "The exposure keeps growing and nothing says so. A backup that stopped running "
            "leaves no error anywhere, because the thing that failed is a job that no longer "
            "happens, and an absent job produces no failed job."
        ),
        every=_DAILY,
        severity=Severity.WOKEN,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="denial_digest",
        symbols=("brain.ops.denial_alerts:digest",),
        guards=(
            "that a colleague who keeps being told there is nothing there is noticed by "
            "somebody who can help, without the alert saying what they were refused"
        ),
        lost_silently=(
            "Somebody locked out of what they need waits until they think to complain, and "
            "somebody walking the estate to find out what exists is refused on every attempt "
            "with nothing anywhere saying so. The gate is doing its job in both cases, which "
            "is why neither produces an error."
        ),
        every=DIGEST_WINDOW,
        cadence_from="brain.ops.denial_alerts:DIGEST_WINDOW",
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="directory_sync",
        symbols=(
            "brain.identity.staff_sync:is_due",
            "brain.identity.staff_sync:due_at",
            "brain.identity.staff_sync:dry_run",
        ),
        guards=(
            "that the roster follows employment: somebody who joins can be given work, "
            "somebody who moves department is judged against the new one, and somebody who "
            "leaves stops holding a role"
        ),
        lost_silently=(
            "The roster freezes at whatever it last said and keeps answering confidently. "
            "A joiner waits, which somebody complains about; a mover and a leaver do not, "
            "and those are the two that quietly leave a role in place."
        ),
        every=SYNC_INTERVAL,
        cadence_from="brain.identity.staff_sync:SYNC_INTERVAL",
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="knowledge_reverification",
        symbols=(
            "brain.knowledge.verification:open_reverification_tasks",
            "brain.knowledge.item:due_for_reverification",
        ),
        guards=(
            "that an answer drawn from something a person once approved is not still being "
            "given long after the approval expired"
        ),
        lost_silently=(
            "Answers keep arriving with a verified badge on them. Staleness has no symptom "
            "at the point of reading: the answer is fluent, sourced and wrong, and the badge "
            "says a person checked it, which was true once."
        ),
        every=DEFAULT_CADENCE,
        cadence_from="brain.knowledge.verification:DEFAULT_CADENCE",
        severity=Severity.NOTICED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="resolution_calibration",
        symbols=("brain.resolution.calibration:due", "brain.resolution.calibration:drift"),
        guards=(
            "that the weights deciding whether two records are the same person stay fitted "
            "to the data as it is now rather than as it was when they were trained"
        ),
        lost_silently=(
            "The matcher keeps returning confident answers at weights nobody has re-fitted. "
            "A drifting matcher does not fail, it merges two people or splits one, and both "
            "read downstream as ordinary data."
        ),
        every=CALIBRATION_PERIOD,
        cadence_from="brain.resolution.calibration:CALIBRATION_PERIOD",
        severity=Severity.NOTICED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="queue_redrive",
        symbols=("brain.ops.queue:verdict_for",),
        guards=(
            "that a job whose worker died underneath it is reclaimed and either retried or "
            "set aside, rather than staying in flight for ever with nothing holding it"
        ),
        lost_silently=(
            "The job sits in a running state that no process is behind. Every queue metric "
            "reports it as work in progress, which is the one reading that makes it invisible "
            "to both of the things that would otherwise find it: it is neither pending nor "
            "failed."
        ),
        every=stale_after(),
        cadence_from="brain.ops.queue:stale_after",
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="side_effect_resume",
        symbols=("brain.ops.idempotency:resume",),
        guards=(
            "that a side effect issued by a process which then died is read back from the "
            "source before anybody decides whether to issue it again"
        ),
        lost_silently=(
            "The operation stays in the state that means nobody knows whether the thing "
            "happened, and the ordinary recovery path is to try again. That is the one "
            "failure in this system that is visible outside it, because the second attempt "
            "is a second real act against somebody else's system."
        ),
        every=stale_after(),
        cadence_from="brain.ops.queue:stale_after",
        severity=Severity.WOKEN,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="audit_anchor",
        symbols=("brain.audit.anchor:take_anchor",),
        guards=(
            "that entries cannot be removed from the end of the audit ledger without it "
            "being detectable, which the hash chain on its own cannot show"
        ),
        lost_silently=(
            "The chain still verifies, because a chain has no idea how long it was meant to "
            "be: delete the newest entries and what remains is perfectly consistent. The "
            "anchor is the only thing that turns that into a detectable fact, and its absence "
            "looks exactly like a quiet week."
        ),
        every=_SIX_HOURLY,
        severity=Severity.RAISED,
        invoked_by=Invocation.ON_A_ROUTE,
        route="/api/audit/anchor",
        schedule_file=".github/workflows/anchor.yml",
    ),
    Control(
        name="model_health_probes",
        symbols=("brain.models.health:next_probes",),
        guards=(
            "that a provider which has stopped answering is found by asking it rather than "
            "by a person's question being the probe"
        ),
        lost_silently=(
            "A breaker that opened stays open, because what closes it is a probe. The lane "
            "keeps working on whatever is left and the estate reads as healthy at reduced "
            "capacity, which is indistinguishable from an estate that was always this size."
        ),
        every=timedelta(seconds=PROBE_INTERVAL_SECONDS),
        cadence_from="brain.models.health:PROBE_INTERVAL_SECONDS",
        severity=Severity.RAISED,
        invoked_by=Invocation.NOTHING,
    ),
    Control(
        name="spend_correction",
        symbols=("brain.ops.spend:correct",),
        guards=(
            "that the cost estimator every budget decision is taken against stays anchored to "
            "what runs actually cost"
        ),
        lost_silently=(
            "Budgets go on being enforced against an estimate nobody has checked. An "
            "estimator that is wrong low waves expensive work through every ceiling in the "
            "system, and every refusal and every admission still reads as a budget working."
        ),
        every=_WEEKLY,
        severity=Severity.NOTICED,
        invoked_by=Invocation.NOTHING,
    ),
)


def control(name: str, controls: Sequence[Control] | None = None) -> Control:
    """One control by name, refusing a name nothing declares.

    Raises rather than returning None, following `brain.ops.reliability.lane_objective`: a
    caller asking about a control that does not exist has a stale name in their hand, and the
    honest answer is the one that stops them rather than the one that reads as "nothing is
    wrong with it".
    """
    rows = CONTROLS if controls is None else tuple(controls)
    for row in rows:
        if row.name == name:
            return row
    msg = f"no control is called {name!r}; declared: {', '.join(sorted(one.name for one in rows))}"
    raise ControlsError(msg)


def orphans(controls: Sequence[Control] | None = None) -> tuple[Control, ...]:
    """Every control nothing calls, in declaration order.

    The list this module exists to produce. Declaration order rather than sorted, because the
    registry is grouped by what a control is for and a reader working down it is reading a
    description of the estate rather than an index.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    return tuple(row for row in rows if row.invoked_by is Invocation.NOTHING)


def cadence_is_declared_elsewhere(one: Control) -> bool:
    """Whether this control's interval came from a name declared beside the mechanism.

    False is not a defect, it is a smaller finding worth being able to see: a mechanism that
    has to run and whose own module says nothing about how often is one where this registry
    is the only statement of its cadence, so the number cannot be tuned beside the code it
    governs. Reported by `advisories` rather than by `registry_gaps`, because it is a gap in
    the other module rather than a disagreement with the source.

    **This was first written as a comparison of values and it was wrong in the flattering
    direction.** It asked whether the control's interval appeared in the set of intervals
    imported here, which two controls can satisfy by coincidence: a day is a day, so
    `retention_sweep` matched `knowledge.verification.DEFAULT_CADENCE` and reported a
    provenance it did not have, and a week did the same through
    `resolution.calibration.CALIBRATION_PERIOD`. Provenance is not a property of a number.
    So the row names where its figure came from and `registry_gaps` checks that the name
    exists; the empty case is the assertion, and it is the one the advisory reports.
    """
    return bool(one.cadence_from)


# ------------------------------------------------------- what the source actually says
def _module_path(symbol: str, src: Path | None = None) -> Path:
    """Where the module half of a symbol lives on disk."""
    module, _, _ = symbol.partition(":")
    root = SRC if src is None else src
    return root.joinpath(*module.removeprefix("brain.").split(".")).with_suffix(".py")


def _module_name(path: Path, src: Path | None = None) -> str:
    """The dotted name of a file under `src/brain`."""
    root = SRC if src is None else src
    return "brain." + ".".join(path.relative_to(root).with_suffix("").parts)


@cache
def _parsed(path: Path) -> ast.Module:
    """One file's syntax tree, parsed once per process.

    Cached because every check below walks the whole tree and there are four hundred files
    in it. A file that does not parse raises rather than being skipped: the tree is broken,
    every other gate is about to say so more clearly than this one would, and swallowing it
    here would turn a broken repository into a registry that quietly stopped seeing a module.
    """
    return ast.parse(path.read_text(encoding="utf-8"))


@cache
def _sources(src: Path | None = None) -> tuple[Path, ...]:
    """Every Python file this repository ships, excluding this registry.

    This module is excluded from every scan below, and the exclusion is load-bearing rather
    than tidy. `CONTROLS` imports each mechanism's own cadence constant, so a scan that
    counted this file would be a scan in which the registry proves the thing it is asking
    about. Imports are not calls, so the exclusion changes no answer today; it is here so
    that it cannot start changing one.

    Cached, for the reason `_call_index` is: this is asked once per symbol per check and the
    tree does not move underneath a running process. A tuple rather than a list because a
    cached mutable answer is one a caller can edit for everybody else.
    """
    root = SRC if src is None else src
    here = Path(__file__).resolve()
    return tuple(
        sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts and p != here)
    )


@cache
def _call_index(src: Path | None = None) -> Mapping[str, frozenset[str]]:
    """Every `module:function` called anywhere in the tree, against the modules calling it.

    Built once and inverted rather than searched per symbol, and that is a measurable
    difference rather than a preference: `registry_gaps` asks about thirty symbols and each
    ask walked four hundred files, which took a minute and a half. One pass answers all of
    them.

    Resolves the two spellings that occur in this repository: `from x import f` followed by
    `f(...)`, wherever the import sits, including inside a function body, which is how
    `brain.docs_routes` reaches `take_anchor`; and `import x` followed by `x.f(...)`. It does
    not resolve a call through an instance, a callable passed as an argument, or anything
    dynamic, and that limit runs in the safe direction for the question being asked: it can
    fail to find a caller, never invent one. A control reported as having no caller is
    therefore worth reading the module for, and every control reported as having one does.

    A module calling its own function is not recorded. That is an implementation detail of
    one file rather than something running it on a schedule, and counting it is how a module
    with a private helper reports itself as wired.
    """
    index: dict[str, set[str]] = {}
    for path in _sources(src):
        here = _module_name(path, src)
        tree = _parsed(path)
        # binding -> the symbol it resolves to, for `from x import f [as g]`
        direct: dict[str, str] = {}
        # binding -> the module it resolves to, for `import x [as y]`
        dotted: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    direct[alias.asname or alias.name] = f"{node.module}:{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    dotted[alias.asname or alias.name] = alias.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            symbol = ""
            if isinstance(called, ast.Name):
                symbol = direct.get(called.id, "")
            elif isinstance(called, ast.Attribute) and isinstance(called.value, ast.Name):
                module = dotted.get(called.value.id, "")
                symbol = f"{module}:{called.attr}" if module else ""
            if symbol and not symbol.startswith(f"{here}:"):
                index.setdefault(symbol, set()).add(here)
    return MappingProxyType({key: frozenset(value) for key, value in index.items()})


def call_sites(symbol: str, src: Path | None = None) -> tuple[str, ...]:
    """Every module under `src/brain` that calls this function, in name order.

    A lookup into `_call_index`, which is where the argument for what this can and cannot
    see is written down.
    """
    return tuple(sorted(_call_index(src).get(symbol, frozenset())))


def missing_symbols(one: Control, src: Path | None = None) -> tuple[str, ...]:
    """The functions this control names that do not exist at module level, in declared order.

    A symbol nobody can resolve is the shape of row that passes every other check by being
    unaskable: `call_sites` finds no callers for a function that is not there either, so a
    typo would present as an orphan and would be believed, because twelve of these are
    orphans.
    """
    return tuple(symbol for symbol in one.symbols if not is_declared(symbol, src))


def _module_level_names(path: Path) -> frozenset[str]:
    """Every name a module binds at its top level: functions, classes and assignments.

    Top level only, and that is what makes it the right question. A name bound inside a
    function or a class body cannot be imported, so a registry naming one is naming
    something no scheduler could reach, which is exactly the row this is looking for.
    """
    found: set[str] = set()
    for node in _parsed(path).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
        elif isinstance(node, ast.Assign):
            found.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return frozenset(found)


def is_declared(symbol: str, src: Path | None = None) -> bool:
    """Whether `module:name` names something that module actually binds at its top level.

    Read from the source rather than imported, following
    `tests/invariants/test_single_implementation.py`: importing to find out would run every
    module in the registry at check time, and a module that raises at import would turn a
    registry check into a crash somewhere else entirely.
    """
    path = _module_path(symbol, src)
    if not path.is_file():
        return False
    _, _, name = symbol.partition(":")
    return name in _module_level_names(path)


def recurrence_predicates(src: Path | None = None) -> tuple[str, ...]:
    """Every module-level function in the tree whose name says it answers "is a run owed".

    The converse half of this registry, and the half that is derived. The control set cannot
    be generated from the code, because nothing distinguishes a mechanism that must run from
    a function that happens to be periodic. What can be generated is this: a predicate that
    exists and belongs to no control is a mechanism somebody scheduled and nobody described,
    which is precisely how a hand-written list falls behind while going on saying that
    everything is fine.

    Module level only. `brain.ops.retention.RetentionReport.due` and
    `brain.ops.jobs.JobRecord.is_due` are properties of a value rather than schedules, and
    including them would put four rows in this list that no scheduler could ever call.
    """
    found: list[str] = []
    for path in _sources(src):
        found.extend(
            f"{_module_name(path, src)}:{node.name}"
            for node in _parsed(path).body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and _RECURRENCE_RE.match(node.name)
        )
    return tuple(sorted(found))


def route_is_declared(path: str, src: Path | None = None) -> tuple[str, ...]:
    """Every module declaring an HTTP route at this path, in name order.

    Read off the decorator's first positional argument rather than by searching the text for
    the path, because the path appears in prose as well: `brain.docs_routes` names the
    workflow that reads it in the handler's own docstring, and a check satisfied by a
    docstring is the failure `sweep_tool_registry` and a `filter="data"` test have both had
    here already.
    """
    found: set[str] = set()
    for source in _sources(src):
        for node in ast.walk(_parsed(source)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue
                first = decorator.args[0]
                if isinstance(first, ast.Constant) and first.value == path:
                    found.add(_module_name(source, src))
    return tuple(sorted(found))


#: A schedule entry in a workflow file. The line rather than the word, so the string `cron`
#: in a comment or a job name does not satisfy it.
_CRON_RE: Final = re.compile(r"^\s*-?\s*cron:\s*\S", re.M)


def externally_scheduled(one: Control, repo: Path | None = None) -> tuple[str, ...]:
    """Every reason this control's external schedule would not fire, empty when it would.

    Three, and each is a way the control is silently not running while the row says it is.
    The file being absent is the loud one. A file with no schedule entry in it is a workflow
    that only ever runs when somebody presses the button, which is the state a schedule
    decays into when somebody is debugging it. And a file that does not name the route is a
    schedule pointed at something else, which is the failure a reader cannot see from either
    end: the workflow is scheduled and the route exists, and they are not connected.

    The file's text is read rather than its YAML parsed. `pyyaml` is a development
    dependency and this module ships, so parsing it would mean either a new runtime
    dependency for one check or an import that fails on an installed system. The cost is
    that a mention of the route in a comment would satisfy the third check, and it is worth
    paying: the file is small, it is ours, and what this is built to catch is the schedule
    being deleted rather than an author working around it.
    """
    root = REPO if repo is None else repo
    if not one.schedule_file:
        return ()
    path = root / one.schedule_file
    if not path.is_file():
        return (
            f"{one.name} is scheduled by {one.schedule_file}, which does not exist, so "
            "nothing outside the process starts it",
        )
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    if not _CRON_RE.search(text):
        findings.append(
            f"{one.schedule_file} carries no schedule entry, so {one.name} runs only when "
            "somebody starts it by hand"
        )
    if one.route and one.route not in text:
        findings.append(
            f"{one.schedule_file} does not name {one.route}, so whatever it is scheduled to "
            f"do is not what reaches {one.name}"
        )
    return tuple(findings)


def measured_invocation(one: Control, repo: Path | None = None) -> Invocation:
    """What the source says starts this control, ignoring what the row claims.

    The route is asked about first, and the order matters. `audit_anchor`'s function is
    called from the module that declares the route, so an in-process check asked first would
    answer `IN_PROCESS` and be technically true and operationally wrong: nothing in this
    process calls that route, and the thing that does is a cron file outside the tree. The
    reader following that answer would go looking for a scheduler in Python.

    Every symbol is required to have a caller before the control counts as in-process; see
    `A_CONTROL_IS_RUN_ONLY_WHEN_ALL_OF_IT_IS`.

    **The module that declares the route has to be one of the callers, and that clause is
    what makes the route answer mean anything.** Without it the check reads "a route with
    this path exists somewhere, and something somewhere calls this function", which two
    unrelated facts satisfy: a control could be declared as reached by a route in one module
    while its function is called from another that the schedule never touches, and the row
    would measure as `ON_A_ROUTE` with no path between the two.
    """
    root = REPO if repo is None else repo
    src = root / "src" / "brain"
    serving = set(route_is_declared(one.route, src)) if one.route else set()
    reached_from_outside = (
        one.route
        and one.schedule_file
        and not externally_scheduled(one, root)
        and serving
        and all(call_sites(symbol, src) for symbol in one.symbols)
        and any(serving & set(call_sites(symbol, src)) for symbol in one.symbols)
    )
    if reached_from_outside:
        return Invocation.ON_A_ROUTE
    if all(call_sites(symbol, src) for symbol in one.symbols):
        return Invocation.IN_PROCESS
    return Invocation.NOTHING


def registry_gaps(
    controls: Sequence[Control] | None = None, repo: Path | None = None
) -> tuple[str, ...]:
    """Every way this registry has stopped describing the code it claims to describe.

    Five findings, and they are the five ways a list of safety mechanisms lies.

    A duplicate name is two rows that alert as one and are handed over as one, and which of
    them a lookup returns depends on the order somebody wrote them in.

    A symbol that does not exist is the row that passes every other check by being
    unaskable, and on a registry where most rows are orphans it would be believed.

    A declared invocation that disagrees with the source is the whole point of the check, and
    it fires in both directions: a control recorded as running that nothing calls is the
    console lying about the estate, and a control recorded as an orphan that something now
    calls is a record that has fallen behind good news, which is how the record stops being
    read at all.

    A route or a schedule file that does not check out is a control declared as started from
    outside the process whose outside half is not there.

    And a recurrence predicate belonging to no control is the converse: something in the tree
    knows when it is due and nothing here says what it protects.

    Both sequences are parameters defaulting to the declared ones, for the reason
    `brain.ops.queue.concurrency_gaps` takes its allocation: a check that can only be run
    against the constants beside it cannot be shown to fail.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    root = REPO if repo is None else repo
    src = root / "src" / "brain"
    findings: list[str] = []

    seen: set[str] = set()
    for row in rows:
        if row.name in seen:
            findings.append(
                f"{row.name!r} is declared twice; the two alert as one control and whichever "
                "is read second silently decides what it guards"
            )
        seen.add(row.name)

    for row in rows:
        findings.extend(
            f"{row.name} names {symbol}, which is not a module-level function in this tree, "
            "so nothing can be asked whether anything calls it"
            for symbol in missing_symbols(row, src)
        )
        findings.extend(externally_scheduled(row, root))
        if row.cadence_from and not is_declared(row.cadence_from, src):
            findings.append(
                f"{row.name} takes its cadence from {row.cadence_from}, which this tree does "
                "not declare, so the number here is now the only one and nothing says so"
            )
        if row.route and not route_is_declared(row.route, src):
            findings.append(
                f"{row.name} is reached at {row.route} and no module declares that route, so "
                "the schedule calling it reaches nothing"
            )

    for row in rows:
        if missing_symbols(row, src):
            # Already reported above, and the measurement would be meaningless: a symbol that
            # does not exist has no callers either, so this row would read as an orphan.
            continue
        measured = measured_invocation(row, root)
        if measured is not row.invoked_by:
            findings.append(
                f"{row.name} is recorded as {row.invoked_by.value} and the source says "
                f"{measured.value}. {A_COMPUTED_ANSWER_CANNOT_NOTICE_THAT_IT_USED_TO_BE_DIFFERENT}"
            )

    described = {symbol for row in rows for symbol in row.symbols}
    predicates = recurrence_predicates(src)
    findings.extend(
        f"{predicate} says when something is due and belongs to no control, so nothing "
        "records what it guards or whether anything runs it. Add a row to CONTROLS, or an "
        "entry to NOT_A_SCHEDULE saying why it is a trigger rather than a schedule"
        for predicate in predicates
        if predicate not in described and predicate not in NOT_A_SCHEDULE
    )
    findings.extend(
        f"{predicate} is exempted by NOT_A_SCHEDULE and no longer exists, so the exemption "
        "is waiting to cover whatever takes that name next"
        for predicate in sorted(NOT_A_SCHEDULE)
        if predicate not in predicates
    )
    return tuple(findings)


def advisories(controls: Sequence[Control] | None = None) -> tuple[str, ...]:
    """Everything worth knowing about this registry that is not a disagreement with the code.

    Separate from `registry_gaps` for the reason `brain.ops.worker.advisories` is separate
    from its preflight: a finding that is real, actionable and not grounds for failing a gate
    needs somewhere to be said out loud, and folding it into the gate is how a gate that
    could be green stops being.

    Three kinds. A control whose cadence is declared nowhere but here, which means the number
    cannot be tuned beside the code it governs. A control whose recurrence lives in a schedule
    file, where the figure here is a *restatement* of a cron expression rather than a
    derivation from one: nothing compares the two, so somebody changing the cron from every
    six hours to every twelve leaves this registry alerting on a window that no longer
    matches, and the alert stays quiet for exactly as long as the mistake lasts. That is a
    real gap and it is said out loud rather than being closed, because closing it means
    parsing cron in a module that ships, and a cron parser written for one line is a second
    thing that can be wrong about the schedule.

    And the orphans, restated as a line each, because a count of them is a number somebody
    reads once and a list is a thing somebody works down.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    findings = [
        f"{row.name} runs every {row.every} and its own module declares no interval, so this "
        "registry is the only statement of its cadence"
        for row in rows
        if not cadence_is_declared_elsewhere(row)
    ]
    findings.extend(
        f"{row.name}'s schedule is a cron expression in {row.schedule_file} and this registry "
        f"restates it as {row.every}; nothing compares the two, so a change to the cron leaves "
        "the alerting window behind it"
        for row in rows
        if row.schedule_file
    )
    findings.extend(
        f"{row.name} guards {row.guards} and nothing calls it. "
        f"{A_MECHANISM_WITH_NO_CALLER_IS_WORSE_THAN_NO_MECHANISM}"
        for row in orphans(rows)
    )
    return tuple(findings)


def chains_worth_checking(
    controls: Sequence[Control] | None = None, repo: Path | None = None
) -> tuple[str, ...]:
    """Controls whose callers are themselves called by nothing, in name order.

    The check `measured_invocation` deliberately does not make, said out loud instead of left
    implied. A control with a caller is not thereby running: the caller may be a function
    nothing calls either, and a chain of three uncalled functions reports as wired at every
    link. `brain.knowledge.verification.open_reverification_tasks` is exactly that shape and
    is how this function came to exist.

    One level rather than a closure, and the limit is honest rather than lazy: a full call
    graph over this tree would have to model methods, callables passed as arguments and route
    registration, and a reachability answer that is wrong in the optimistic direction is
    worse than no answer at all. One level is the depth at which the answer is still exact.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    root = REPO if repo is None else repo
    src = root / "src" / "brain"
    findings: list[str] = []
    for row in rows:
        if row.invoked_by is Invocation.NOTHING:
            continue
        for symbol in row.symbols:
            for caller in call_sites(symbol, src):
                onward = _callers_of_module(caller, src)
                if not onward:
                    findings.append(
                        f"{row.name}: {symbol} is called from {caller}, which nothing else "
                        "in this tree imports, so the caller is as unreached as the control"
                    )
    return tuple(sorted(set(findings)))


def _callers_of_module(module: str, src: Path | None = None) -> tuple[str, ...]:
    """Every module importing this one, in name order. Used only by `chains_worth_checking`."""
    found: set[str] = set()
    for path in _sources(src):
        here = _module_name(path, src)
        if here == module:
            continue
        for node in ast.walk(_parsed(path)):
            from_it = isinstance(node, ast.ImportFrom) and node.module == module
            of_it = isinstance(node, ast.Import) and any(
                alias.name == module for alias in node.names
            )
            if from_it or of_it:
                found.add(here)
    return tuple(sorted(found))


# ------------------------------------------------------ a control that has not run (M37.5.1.3)
class Missed(enum.StrEnum):
    """Why a control has not run recently enough. Four, and each sends a person elsewhere.

    That is the test for a member rather than tidiness of vocabulary, following
    `brain.ops.jobs.DeadLetterReason`: two reasons that lead to the same action are one
    reason with two names, and a reader triaging a screen learns to ignore the column.
    """

    #: Nothing calls it, so there is no schedule to have failed. See
    #: `NOTHING_CALLS_IT_IS_NOT_THE_SAME_ALERT_AS_IT_IS_LATE`.
    UNREACHABLE = "unreachable"
    #: Nothing is recording runs of it. The mechanism may be running perfectly.
    NOT_RECORDED = "not_recorded"
    #: Runs are recorded and there has never been one.
    NEVER_RUN = "never_run"
    #: It ran, and not recently enough.
    BEHIND = "behind"


@dataclass(frozen=True)
class Overdue:
    """One control that has not run, and everything needed to act on it.

    Carries no count of anything and names no principal, entity or field: what it says is the
    name of a mechanism, what that mechanism is for, and how long. Every one of those is a
    fact about the product rather than about the company running it, which is what makes this
    safe to forward, and `brain.ops.alerting.disclosure_findings` is asked of the text rather
    than the property being promised.
    """

    control: Control
    missed: Missed
    severity: Severity
    #: How far past its alerting threshold, or None when it has never run or is not recorded.
    late_by: timedelta | None
    text: str


def _overdue_text(one: Control, missed: Missed, late_by: timedelta | None) -> str:
    """The sentence an operator reads. Built from the control rather than written per row.

    Derived so that a control added to the registry arrives with its alert text already
    correct, and so the wording cannot drift between thirteen near-identical paragraphs. The
    two hand-written sentences on the control are what make each one specific.
    """
    lateness = f"{late_by} past the point where a missed run is worth saying" if late_by else ""
    reason = {
        Missed.UNREACHABLE: (
            "nothing in this installation calls it, so there is no schedule to look at and "
            "starting it by hand will not keep it running"
        ),
        Missed.NOT_RECORDED: (
            "nothing is recording its runs, so it may be running perfectly and there is no "
            "way to tell from here"
        ),
        Missed.NEVER_RUN: "its runs are recorded and there has not been one",
        Missed.BEHIND: f"its last run is {lateness}",
    }[missed]
    return (
        f"{one.name} guards {one.guards}. It should run every {one.every} and {reason}. "
        f"Until it does: {one.lost_silently}"
    )


def overdue(
    *,
    last_run: Mapping[str, datetime | None],
    now: datetime,
    controls: Sequence[Control] | None = None,
) -> tuple[Overdue, ...]:
    """Every control that is not running, loudest first (M37.5.1.3).

    Unreachable is decided before lateness and never by it, which is the ordering that makes
    the alert useful. A control nothing calls is late on every pass for ever, and reporting
    that as "the schedule did not fire" sends a person to the one place with nothing in it.
    See `NOTHING_CALLS_IT_IS_NOT_THE_SAME_ALERT_AS_IT_IS_LATE`.

    A last run in the future is not late. That is clock skew between whatever recorded the
    run and whatever is asking, and the conservative reading of a timestamp ahead of `now` is
    silence, which is the reading `brain.ops.denial_alerts.digest` takes for the same shape.

    Sorted by severity descending, following `brain.ops.recovery.alerts`: a reader triaging
    at three in the morning reads down, and declaration order would put a knowledge badge
    above a side effect that may have happened twice.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    found: list[Overdue] = []
    for row in rows:
        missed: Missed
        late_by: timedelta | None = None
        if row.invoked_by is Invocation.NOTHING:
            missed = Missed.UNREACHABLE
        elif row.name not in last_run:
            missed = Missed.NOT_RECORDED
        else:
            seen = last_run[row.name]
            if seen is None:
                missed = Missed.NEVER_RUN
            elif now - seen <= row.alert_after:
                continue
            else:
                missed = Missed.BEHIND
                late_by = now - seen - row.alert_after
        found.append(
            Overdue(
                control=row,
                missed=missed,
                severity=row.severity,
                late_by=late_by,
                text=_overdue_text(row, missed, late_by),
            )
        )
    return tuple(sorted(found, key=lambda one: (-one.severity, one.control.name)))


# ------------------------------------------------------------- the runbooks (M37.5.2.2)
#: What to check and what to do, per reason a control has not run. Exhaustive over `Missed`,
#: and `runbook_gaps` keeps it that way.
#:
#: Keyed by reason rather than by control, and that is a decision rather than an economy.
#: Thirteen runbooks differing only in a module name are thirteen paragraphs that drift, and
#: the drift is invisible because nobody reads twelve of them. What is genuinely specific to
#: a control is its entry point, its cadence and what it guards, and every one of those is on
#: the row already, so `runbook_for` puts them in.
_RUNBOOK_STEPS: Final[Mapping[Missed, tuple[tuple[str, ...], tuple[str, ...]]]] = MappingProxyType(
    {
        Missed.UNREACHABLE: (
            (
                "Confirm from the control registry that nothing calls it. This is not a "
                "schedule that failed; there is no schedule.",
                "Check whether the console is reporting the guarantee it protects as being "
                "in force, because that is the reading that has to be corrected first.",
            ),
            (
                "Tell whoever owns the installation that the guarantee is not currently "
                "held, before anything else is done.",
                "Do not start it by hand and consider it resolved: one run does not make it "
                "a control, and a single run is what makes it look resolved.",
                "Escalate: wiring a control up is a change to the software rather than to "
                "this installation.",
            ),
        ),
        Missed.NOT_RECORDED: (
            (
                "Check whether the mechanism is running and only its record keeping is "
                "missing, which is the likely case and the harmless one.",
                "Check whether the name in the registry matches the name whatever records "
                "runs is writing, because a rename on one side produces exactly this.",
            ),
            (
                "Reconcile the two names, so that the next pass reports the mechanism "
                "rather than the gap in the recording.",
                "Until they agree, treat the control as unverified rather than as working.",
            ),
        ),
        Missed.NEVER_RUN: (
            (
                "Check whether this installation has been running for longer than the "
                "control's own interval, because a fresh install has legitimately never run "
                "most of these.",
                "Check the schedule for an entry naming the control's entry point.",
            ),
            (
                "Start one run by hand and confirm from the record that it was written.",
                "Fix the schedule, because a run started by hand answers the question and "
                "does not answer the next one.",
            ),
        ),
        Missed.BEHIND: (
            (
                "Check whether the last run failed or never started, which are different "
                "problems with different fixes.",
                "Check whether anything else on the same schedule is also behind, because "
                "one late control is the mechanism and several is the scheduler.",
            ),
            (
                "Start one run by hand so the guarantee is held again now.",
                "Then find out why the scheduled one did not, because the hand-started run "
                "has removed the symptom and not the cause.",
            ),
        ),
    }
)


def runbook_for(one: Control, missed: Missed) -> Runbook:
    """What the person who received this alert does about it.

    Assembled from the reason's steps and the control's own facts rather than written out
    thirteen times. The first check is always the control's own identity, because the reader
    has an alert naming a mechanism they may never have heard of, and the first thing they
    need is what it is for and what it is called in the source.

    `escalate_after` is derived from the route's acknowledgement window rather than declared,
    so a runbook cannot be written that escalates while the first responder is still inside
    the time they were given. `brain.ops.alerting.runbook_gaps` is the check that would catch
    it, and deriving it is what makes the check green by construction rather than by care.
    """
    first, then = _RUNBOOK_STEPS[missed]
    route = route_for(one.severity)
    return Runbook(
        first_check=(
            f"{one.name} guards {one.guards}. Its entry point is {one.entry_point} and it "
            f"should run every {one.every}.",
            *first,
        ),
        then_do=then,
        escalate_after=route.acknowledge_within * ESCALATE_AFTER_UNANSWERED,
    )


def runbook_gaps(controls: Sequence[Control] | None = None) -> tuple[str, ...]:
    """Every alert this registry can raise that has no runbook behind it.

    Asked over the product of the controls and the reasons rather than over the reasons
    alone, because that product is the set of alerts a person can actually receive, and a
    reason covered for twelve controls and not the thirteenth is a gap that only appears
    during the incident on the thirteenth.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    findings: list[str] = []
    for row in rows:
        for missed in Missed:
            if missed not in _RUNBOOK_STEPS:
                findings.append(
                    f"{row.name} can be reported as {missed.value} and nothing says what to "
                    "do about it, so the alert arrives with no next step"
                )
                continue
            book = runbook_for(row, missed)
            findings.extend(
                f"{row.name}/{missed.value}: {problem}"
                for problem in _alerting_runbook_gaps(book, row.severity)
            )
    return tuple(findings)


def _alerting_runbook_gaps(book: Runbook, severity: Severity) -> tuple[str, ...]:
    """`brain.ops.alerting.runbook_gaps` against this severity's route.

    A wrapper rather than a call at each site, so the route is resolved in one place and a
    severity nothing routes raises here rather than in the middle of a list comprehension.
    """
    return route_runbook_gaps(book, route_for(severity))


# ------------------------------------------------------- the handover pack (M37.4.3.4)
#: Which part of an installation this registry is a description of. Named from
#: `brain.ops.handover.Residue` rather than written out, so the handover pack and the
#: teardown enumerate the same thing: a scheduled job that fires after the client has left is
#: the residue that module refuses to certify a handover without.
HANDOVER_RESIDUE: Final[Residue] = Residue.SCHEDULED_WORK


def handover_lines(controls: Sequence[Control] | None = None) -> tuple[str, ...]:
    """The scheduled job registry, in the form it is handed over (M37.4.3.4).

    One line per control: what it is called, what it protects, how often it runs, and
    **whether anything calls it today**. The last part is what makes this a handover rather
    than a brochure. A pack that lists thirteen mechanisms as protecting an estate that
    twelve of them are not running is worse than no pack: the client reads it, believes the
    estate is covered, and stops asking. `brain.ops.recovery.A_BACKUP_NOBODY_HAS_RESTORED_IS_A_FILE`
    is the same sentence about a different artefact.

    Declaration order, matching `orphans`: the registry is grouped by what a control is for,
    and a client reading down it is reading a description of their installation.
    """
    rows = CONTROLS if controls is None else tuple(controls)
    return tuple(
        f"{row.name}: runs every {row.every}, guards {row.guards}. Started by: {_started_by(row)}."
        for row in rows
    )


def _started_by(one: Control) -> str:
    """How a control's invocation reads in a handover pack, in words rather than a code."""
    if one.invoked_by is Invocation.ON_A_ROUTE:
        return f"a schedule in {one.schedule_file} calling {one.route}"
    if one.invoked_by is Invocation.IN_PROCESS:
        return f"this installation, through {one.entry_point}"
    return (
        "NOTHING. The mechanism is present and tested and no schedule runs it, so the "
        "guarantee above is not currently held"
    )
