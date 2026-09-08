"""When a scaling move becomes due, and what parallelism over source calls is bounded by.

Two halves, and they are here together because they fail the same way. A scaling move is
triggered by a threshold, parallelism is bounded by a ceiling, and **both are numbers that are
right for the company that wrote them and wrong for the next one**. This repository is the
template rather than one company's system, so a figure chosen by taste here is not a rough
edge; it is a wrong answer shipped to everybody who installs afterwards, and it is a wrong
answer nobody can see, because a threshold looks exactly as authoritative whether it was
measured or preferred.

**So there is nowhere in this module to write a threshold.** `ScalingTrigger` has no float
field. It carries a `ThresholdAnchor`, which names a value declared somewhere else and says
what unit it is in, and a `multiple`, and the threshold is a property computed from the two. A
trigger that cannot be expressed that way carries `ThresholdBasis.NOT_ANCHORED`, no threshold
at all, and appears in `unanchored()`, which is the list somebody has to read before believing
the table. That construction is `brain.locale.Deferral`'s applied to a number rather than to a
feature: a deferral with an empty trigger is the word "later" in a dataclass, and a threshold
with an empty anchor is the word "about" in one. See
`A_THRESHOLD_WITH_NO_ANCHOR_IS_A_NUMBER_SOMEBODY_LIKED`.

The four moves and what each is anchored to:

*Partition the ledger.* Due when the retained window is longer than one partition, which is
`brain.ops.partitioning.PARTITION_INTERVAL`. It is true for every window and every install,
and that is the finding rather than a defect in the trigger: **partitioning is due at the
moment the table is created and not at a row count**, because converting a populated table to
a partitioned one rewrites it under an exclusive lock. A row-count trigger for this move can
only ever fire late. See `PARTITIONING_IS_DUE_AT_CREATION_AND_A_ROW_COUNT_FIRES_LATE`.

*A read replica.* Due when console reads in flight exceed what the interactive connection pool
has left after the answer path's own peak. Both halves come from `brain.ops.admission`:
`ClassPools.interactive` is the pool, and Little's law over a `CapacityProfile` is the answer
path's occupancy. Nothing is chosen here, which is why the trigger is computed from the
install rather than declared as a figure.

*Materialised reports.* Due when a report's p95 passes `brain.ops.reliability.ANSWER_P95_MS`.
M36.1.3.3 says two seconds and **two seconds is anchored to nothing in this repository**. The
figure that is anchored is the answer lane's own promise: a console report is a screen a person
is waiting at, and the estate has already decided what it owes a person waiting. It is four
times the leaf's number, and saying so is more useful than adopting a figure whose derivation
nobody can reproduce. See `THE_LEAFS_TWO_SECONDS_IS_NOT_DERIVED_FROM_ANYTHING_HERE`.

*Split the hosts.* Due when the profile the install wants does not fit, which
`brain.ops.wiring.budget_breaches` already answers from measured host memory. The second half
of M36.1.4.3, "or a resilience requirement", is the one `NOT_ANCHORED` row in the table: it is
a decision about tolerating a single machine's failure and there is no observable here that
fires it.

The other half of the module is source fan-out, and the first thing to say about it is what is
already built.

**M36.2.1 is `brain.connectors.federation`, which has been there since M11.5.** `SourceCall`
carries `depends_on`, `FanOutPlan` refuses a cycle and computes `waves()`, and
`critical_path_ms` is the longest chain rather than the sum, with `sequential_ms` beside it for
the comparison. That is the dependency graph over independent source calls and the one critical
path, written and tested, and this module does not declare a second `SourceCall`, a second plan
or a second critical path. It was about to: the first draft of this file had all three, and
they read as reasonable until somebody grepped for the name.

**M36.2's graph is not `brain.orchestration.plan`'s graph either, and the difference is the
edge weight.** Structurally the two are the same: a directed acyclic graph, waves, a longest
chain. `Edge.coupling_tokens` there is the context a split would duplicate, because splitting
agent subtasks across child runs makes each child re-establish what the single loop carried.
Two source calls issued concurrently from one loop duplicate nothing, so every source plan
would have a cost multiplier of exactly one and the fan-out gate's cost condition would pass
unconditionally. What bounds source fan-out is contention, and contention is not an edge: two
calls to one connector share a ceiling while sharing no dependency. That is a per-connector cap
over nodes, and giving `DependencyGraph` a vocabulary for it would change what an edge means in
the module that gates agent fan-out. See
`THE_GRAPH_IS_FEDERATIONS_AND_THE_CONTENTION_IS_NOBODYS`.

**What is genuinely missing is the estate, and its absence makes a passing check optimistic.**
`FanOutPlan.critical_path_ms` costs a wave at its slowest member, which is right if the whole
wave starts at once. Whether it can is `brain.ops.admission`'s question, and nothing asked it:
a wave of eight Xero calls against a per-connector ceiling of five takes two rounds, and
`assert_within` passes the plan anyway because it is counting a wave it assumes is one round.
`contended_critical_path_ms` is that correction, expressed as an addition to federation's own
number rather than as a second wall clock, and `fanout_refusals` is where a plan that is
affordable per question and unaffordable per machine is reported. See
`A_WAVE_COSTS_ITS_SLOWEST_MEMBER_ONLY_IF_ALL_OF_IT_CAN_START`.

**Per-connector budgets are read from `brain.ops.admission.headroom`, and there is no global one
to read.** `Resource.SOURCE_CALLS` is in `PER_CONNECTOR`, so every row is keyed by connector and
the estate declares no total. Three measured connectors at eight, five and eight is twenty-one
calls that may be in flight at once with nothing capping the sum, plus four more for every
connector falling back to the default row. `implied_global_ceiling` is what actually binds today
and `scaling_gaps` reports that nobody chose it, rather than this module inventing a number and
presenting it as policy.

**There are two coalescing keys in this repository and they disagree about entitlements on
purpose.** `brain.connectors.federation.flight_key` deliberately holds no reach, because a
connector does not decide what a caller may see: one fetch's rows are the same rows for
everybody and the redactor runs per caller afterwards, so putting an entitlement hash there
would defeat coalescing in exactly the case it exists for. `brain.gate.cache_key.cache_key`
deliberately requires one, because by then the rows have been redacted under somebody's reach.
M36.2.3 is the second of those, so `may_share` compares cache keys and declares no key of its
own. See `A_SHARED_EXECUTION_IS_A_CACHE_ENTRY_THAT_HAS_NOT_FINISHED_YET` and
`SIMILAR_REACH_IS_NOT_EQUAL_REACH`, and read them together: the pair of rules is the thing a
future reader is most likely to try to harmonise.

Rejected: a `ScalingTrigger` carrying a plain threshold with the anchor as prose beside it. It
is what every table of this kind looks like and it is the arrangement in which the prose stays
true while the number stops being, which `brain.ops.wiring.HOST_HEADROOM_MIB` did for as long as
it was a constant with a paragraph and nothing checking either.

Rejected: replacing `FanOutPlan.critical_path_ms` with a contention-aware version. It is the
tidier arrangement and it would put two wall-clock arithmetics over one plan in one repository,
disagreeing first on exactly the plans nobody tested. The contention is an addition to
federation's number, and it is zero when nothing is contended.

Rejected: reducing an over-large wave by a fairness rule. Proportional shares and round-robin
are both defensible and neither is derivable, so the rule would be the one number in the
fan-out arithmetic that nobody could argue with. The plan's own order is the priority instead,
which puts the choice where the knowledge is. See `THE_CALLERS_ORDER_IS_THE_PRIORITY`.

Rejected: measuring anything. Nothing here reads a clock, opens a connection or counts a row,
which is the split `brain.ops.limits` and `brain.ops.limit_store` make. A trigger that owned its
own observations could not be tested for the case that matters, which is the decision taken
against a stale reading.

Task ids: M36.1.1.4, M36.1.2.4, M36.1.3.3, M36.1.4.3, M36.2.1.3, M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Final

from brain.connectors.federation import (
    FANOUT_BUDGET_MS,
    CallBudget,
    FanOutPlan,
    FlightRole,
    SourceCall,
)
from brain.gate.cache_key import CacheKeyParts, cache_key, is_volatile
from brain.ops.admission import (
    Budget,
    CapacityProfile,
    CapacityState,
    ClassPools,
    Resource,
    WorkloadClass,
    budget_for,
    headroom,
    little_law_concurrency,
)
from brain.ops.partitioning import PARTITION_INTERVAL, longest_days
from brain.ops.reliability import ANSWER_P95_MS
from brain.ops.wiring import budget_breaches


class ScalingError(Exception):
    """Raised when a trigger, a fan-out plan or a shared execution cannot mean what it says."""


# ------------------------------------------------------------------ written-down reasons
#: Why `ScalingTrigger` has no field a number can be typed into.
A_THRESHOLD_WITH_NO_ANCHOR_IS_A_NUMBER_SOMEBODY_LIKED: Final = (
    "A scaling trigger reads as authority whatever produced it. Nobody reviewing a dashboard "
    "can tell a threshold that was measured from one that felt about right, and the second "
    "kind is right for exactly one estate: the one whose author was thinking of it. This "
    "repository ships to companies nobody here has met, so a preference committed as a "
    "constant is a wrong answer installed everywhere with nothing that would ever report it. "
    "The threshold is therefore a property rather than a field, computed from a value declared "
    "in another module and a multiple stated beside it, and a trigger whose number cannot be "
    "produced that way carries no number at all and is listed as an open question instead."
)

#: Why the partition trigger fires for every install, and why that is the answer.
PARTITIONING_IS_DUE_AT_CREATION_AND_A_ROW_COUNT_FIRES_LATE: Final = (
    "Converting a populated table to a partitioned one rewrites it: a new parent, a copy of "
    "every row, and an exclusive lock for the duration, on the table every request writes to. "
    "The row count at which that stops being affordable is reached long before anybody puts a "
    "ledger size on a dashboard, so a row-count trigger for this move can only ever fire after "
    "the cheap moment has gone. The honest trigger is the retained window against one partition "
    "interval, which is true at creation for every window this policy would ever declare, and "
    "the row projection is worth publishing at install time as a size rather than as an alarm."
)

#: Why the report threshold is the answer lane's promise and not the leaf's figure.
THE_LEAFS_TWO_SECONDS_IS_NOT_DERIVED_FROM_ANYTHING_HERE: Final = (
    "M36.1.3.3 says a report exceeding two seconds. Nothing in this repository produces two "
    "seconds: the declared figures are a fast lane at 500ms and an answer lane at 8000ms, and "
    "two is neither, nor a stated fraction of either. What can be derived is that a console "
    "report is a screen somebody is waiting at, and the estate has already written down what "
    "it owes a person waiting. So the trigger is the answer lane's own promise, it is four "
    "times the leaf's number, and the difference is recorded rather than split: adopting two "
    "seconds would put a figure in the table whose derivation nobody could reproduce, which is "
    "the whole failure this module is arranged to prevent."
)

#: Where the source-call graph lives, and what this module adds instead of a second one.
THE_GRAPH_IS_FEDERATIONS_AND_THE_CONTENTION_IS_NOBODYS: Final = (
    "brain.connectors.federation.FanOutPlan is the dependency graph over source calls: it holds "
    "SourceCall with depends_on, refuses a cycle, groups the calls into waves and reports the "
    "longest chain rather than the sum. brain.orchestration.plan.DependencyGraph is the same "
    "structure over agent subtasks with a different weight on an edge, coupling being the "
    "context a split would duplicate, which is zero for two calls issued concurrently from one "
    "loop. Neither is reimplemented here. What neither holds is contention: two calls to one "
    "connector share a ceiling while sharing no dependency, so it is a cap over nodes rather "
    "than a weight on an edge, and it is the one thing a plan's wall clock is missing."
)

#: Why a plan inside its budget can still miss it.
A_WAVE_COSTS_ITS_SLOWEST_MEMBER_ONLY_IF_ALL_OF_IT_CAN_START: Final = (
    "FanOutPlan.critical_path_ms costs a wave at its slowest member, which is the whole point "
    "of fanning out and is true exactly when the whole wave starts at once. Whether it can is "
    "a question about the machine rather than about the plan, and brain.ops.admission is where "
    "that is decided: a wave of eight calls to one connector against a per-connector ceiling of "
    "five takes two rounds, and the second round is a whole extra timeout of wall clock. So "
    "assert_within passes a plan that will not meet its budget on a busy afternoon, and nothing "
    "reports it, because the check and the ceilings never met."
)

#: Why an over-large wave is trimmed in the plan's order rather than fairly.
THE_CALLERS_ORDER_IS_THE_PRIORITY: Final = (
    "A wave with more calls than the ceilings admit has to leave some for the next round, and "
    "every fairness rule for choosing which is defensible and none is derivable. Round-robin "
    "across connectors, proportional shares, longest-first: each produces a different plan and "
    "nothing outside the choice says which is right, so the rule would become the one number "
    "in this arithmetic that could not be argued with. The calls are taken in the order the "
    "plan declared them instead, which is stable between two readings of one plan and puts the "
    "priority decision where the knowledge about the question is."
)

#: Why sharing an in-flight answer is the cache's question and not a new one.
A_SHARED_EXECUTION_IS_A_CACHE_ENTRY_THAT_HAS_NOT_FINISHED_YET: Final = (
    "Two callers who may be served one cached answer are exactly the two who may be served one "
    "answer that is still being computed, because the only difference between the two cases is "
    "when they arrived. So the sharing rule is brain.gate.cache_key.cache_key, which already "
    "decides it for the stored case, rather than a second key declared here. A second key would "
    "be a second answer to which two callers are the same caller, and the two would disagree "
    "first on whichever part one of them forgot: the agent configuration, the policy epoch or "
    "the source epochs, each of which changes what an answer says without changing the question."
)

#: Why a shared execution needs equal reach where a shared fetch does not.
SIMILAR_REACH_IS_NOT_EQUAL_REACH: Final = (
    "Two callers whose reaches overlap are not two callers who may be served one answer. "
    "Whichever executes first decides what the shared result was computed under, so if the "
    "wider reach runs, the narrower caller is shown rows they may not see, and if the narrower "
    "runs, the wider caller is told nothing was found for records they are entitled to. The "
    "first is a permission failure and the second is the DENIED and ABSENT rule broken from the "
    "other side, and neither is visible afterwards, because a coalesced request leaves one "
    "execution and two satisfied callers. This is the opposite of the rule one layer down, and "
    "both are right: brain.connectors.federation.flight_key holds no reach because a connector "
    "returns unredacted rows that the redactor then narrows per caller, and by the time an "
    "answer exists the narrowing has happened and belongs to one reach."
)

#: Why a question that may not be cached may not be shared either.
A_QUESTION_TOO_VOLATILE_TO_CACHE_IS_TOO_VOLATILE_TO_SHARE: Final = (
    "brain.gate.cache_key.is_volatile refuses to key a question whose answer is true only at "
    "the moment it is asked. Sharing one is the same mistake with a shorter window rather than "
    "a different one: an execution is seconds long, so the follower is handed a figure computed "
    "before they asked, which is precisely what a volatile question must not be answered with. "
    "The window being short is not a defence, because nothing in the domain layer knows how "
    "short it was."
)

#: Why a refusal to share names the field and never the values.
A_SHARE_REFUSAL_NAMES_THE_FIELD_AND_NEVER_THE_VALUES: Final = (
    "An operator asking why two requests did not share an execution needs to know which part "
    "differed. They do not need the values, and one of the parts is somebody's question. A "
    "message quoting the two keys would put a pair of questions, and the fact that two named "
    "people asked nearly the same thing, into an operational log with its own retention, which "
    "is what brain.ops.jobs.DeadLetter and brain.orchestration.fanout refuse for the same "
    "reason."
)

#: Why the global source-call ceiling is reported rather than invented.
NOBODY_DECLARED_A_TOTAL_FOR_SOURCE_CALLS: Final = (
    "brain.ops.admission puts SOURCE_CALLS in PER_CONNECTOR, so every budget row is keyed by "
    "connector and there is no global row. The total that actually binds is therefore the sum "
    "of the per-connector ceilings, which is a number that arrives by addition rather than by "
    "anybody deciding it, and which grows every time a connector is added. Choosing one here "
    "would be this module setting a global budget in a repository whose whole argument is that "
    "budgets are configuration rows in one place, so the implied total is computed, used, and "
    "reported as undeclared."
)


# ---------------------------------------------------------------------------- the anchors
@dataclass(frozen=True)
class ThresholdAnchor:
    """A value declared somewhere else, which a threshold is computed from.

    `source` is the dotted name of the thing, `value` is what it holds and `unit` is what that
    is measured in. All four fields are required, and `trigger_gaps` checks that `source` does
    not name this module, because an anchor pointing at the module it is anchoring is a number
    agreeing with itself, which is the failure `brain.ops.wiring.HOST_HEADROOM_MIB` had for as
    long as its only test re-derived it from itself.
    """

    source: str
    value: float
    unit: str
    because: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            msg = "an anchor with no source is a number with a paragraph beside it"
            raise ScalingError(msg)
        if not self.unit.strip():
            msg = (
                f"{self.source} states no unit, so a threshold computed from it compares "
                "a reading against a bare number"
            )
            raise ScalingError(msg)
        if not self.because.strip():
            msg = f"{self.source} says nothing about why it is the right thing to anchor to"
            raise ScalingError(msg)


class ScalingMove(enum.StrEnum):
    """The four scaling moves M36.1 names. One per task group, in the order the group is in."""

    PARTITION_THE_LEDGER = "partition_the_ledger"
    READ_REPLICA = "read_replica"
    MATERIALISED_REPORTS = "materialised_reports"
    SPLIT_THE_HOSTS = "split_the_hosts"


class ScalingObservable(enum.StrEnum):
    """What is watched for each move. A member here is something an install can be asked.

    Members rather than sentences, for the reason `brain.locale.Trigger`'s are: "when it gets
    slow" is not something anybody can evaluate, and a trigger carrying one is an intention
    with better manners.
    """

    #: How long the class the table holds is retained, in days.
    RETAINED_WINDOW_DAYS = "retained_window_days"
    #: Console reads holding an interactive connection at once.
    CONSOLE_READS_IN_FLIGHT = "console_reads_in_flight"
    #: The 95th percentile a console report comes back in.
    REPORT_P95_MS = "report_p95_ms"
    #: Whether the profile the install wants fits the host's memory.
    PROFILE_DOES_NOT_FIT = "profile_does_not_fit"
    #: Whether a single machine's failure is acceptable. Nothing here measures this.
    SINGLE_HOST_FAILURE_IS_ACCEPTABLE = "single_host_failure_is_acceptable"


class ThresholdBasis(enum.StrEnum):
    """Where a trigger's number comes from, so `threshold is None` never means two things.

    The construction is `brain.ops.retention.Lifetime`'s: a reader handed None for both "this
    depends on the install" and "nobody has anchored this" cannot tell which they are looking
    at, and the difference is the entire point of the table.
    """

    #: An anchor and a multiple. `threshold` is their product.
    FROM_A_DECLARED_FIGURE = "from_a_declared_figure"
    #: Computed per install from more than one declared figure. `computed_by` names how.
    FROM_THE_INSTALL = "from_the_install"
    #: Nothing here derives it, and that is the finding rather than an omission.
    NOT_ANCHORED = "not_anchored"


@dataclass(frozen=True)
class ScalingTrigger:
    """When one move becomes due, with nowhere to write a number that came from taste.

    See `A_THRESHOLD_WITH_NO_ANCHOR_IS_A_NUMBER_SOMEBODY_LIKED`. `threshold` is a property and
    not a field, so the only number this dataclass accepts is `multiple`, which states how the
    threshold relates to the anchor and is one wherever the threshold is the anchor itself.
    """

    move: ScalingMove
    observable: ScalingObservable
    basis: ThresholdBasis
    unit: str
    because: str
    anchor: ThresholdAnchor | None = None
    #: What the anchor is multiplied by. One means the threshold is the anchored value.
    multiple: float = 1.0
    #: The function in this module that computes the threshold for an install.
    computed_by: str = ""

    def __post_init__(self) -> None:
        if not self.unit.strip():
            msg = f"the {self.move.value} trigger states no unit for {self.observable.value}"
            raise ScalingError(msg)
        if not self.because.strip():
            msg = f"the {self.move.value} trigger says nothing about why it is the right one"
            raise ScalingError(msg)
        if self.multiple <= 0:
            # Zero is how "never fires" is spelled by accident and a negative multiple is a
            # threshold below every reading, so both are triggers that read as configured and
            # are switched off. Turning a move off is a decision and belongs in the table as
            # the absence of a row, where somebody sees it.
            msg = (
                f"the {self.move.value} trigger multiplies its anchor by {self.multiple}, which "
                "is a threshold nothing can cross in the direction it is watched"
            )
            raise ScalingError(msg)
        if (self.anchor is None) is (self.basis is ThresholdBasis.FROM_A_DECLARED_FIGURE):
            msg = (
                f"the {self.move.value} trigger is {self.basis.value} and "
                f"{'carries' if self.anchor is not None else 'carries no'} anchor; a declared "
                "figure needs one and nothing else may have one, or the table shows a number "
                "beside a basis saying the number is not consulted"
            )
            raise ScalingError(msg)
        if bool(self.computed_by.strip()) is not (self.basis is ThresholdBasis.FROM_THE_INSTALL):
            msg = (
                f"the {self.move.value} trigger is {self.basis.value} and names "
                f"{self.computed_by!r} as what computes it; only a trigger computed from the "
                "install names a function, and one that is has to name it or the threshold is "
                "a claim with nothing behind it"
            )
            raise ScalingError(msg)

    @property
    def threshold(self) -> float | None:
        """The number the observable is compared against, or None where there is not one."""
        return None if self.anchor is None else self.anchor.value * self.multiple


# ------------------------------------------------------------------- the anchored figures
#: One partition of the ledger, in days. From `brain.ops.partitioning`, which derives the
#: interval from the retention window and the backup window rather than choosing it.
PARTITION_ANCHOR: Final = ThresholdAnchor(
    source="brain.ops.partitioning.PARTITION_INTERVAL",
    value=float(longest_days(PARTITION_INTERVAL)),
    unit="days",
    because=(
        "a retained window no longer than one partition is a table that is one partition, so "
        "partitioning it changes nothing; anything longer is a table that has to be cut, and "
        "the interval is itself derived from the retention and backup windows"
    ),
)

#: What the estate promises a person waiting, in milliseconds, from the reliability objectives.
REPORT_ANCHOR: Final = ThresholdAnchor(
    source="brain.ops.reliability.ANSWER_P95_MS",
    value=float(ANSWER_P95_MS),
    unit="ms",
    because=(
        "a console report is a screen somebody is waiting at, and the answer lane's objective "
        "is the only figure here that says what this system owes a person waiting; a report "
        "slower than that is slower than the thing the whole system exists to do"
    ),
)

#: The host memory check, as a count of breaches rather than a size. Anything above zero is a
#: profile the measured host cannot honour, and `brain.ops.wiring` is where the measurement is.
HOST_ANCHOR: Final = ThresholdAnchor(
    source="brain.ops.wiring.budget_breaches",
    value=0.0,
    unit="breaches",
    because=(
        "the breach count is arithmetic over measured host memory, the neighbours' "
        "reservations and the deployed baseline, so a profile that breaches does not fit the "
        "machine rather than looking tight to somebody"
    ),
)


TRIGGERS: Final[tuple[ScalingTrigger, ...]] = (
    ScalingTrigger(
        move=ScalingMove.PARTITION_THE_LEDGER,
        observable=ScalingObservable.RETAINED_WINDOW_DAYS,
        basis=ThresholdBasis.FROM_A_DECLARED_FIGURE,
        unit="days",
        anchor=PARTITION_ANCHOR,
        because=PARTITIONING_IS_DUE_AT_CREATION_AND_A_ROW_COUNT_FIRES_LATE,
    ),
    ScalingTrigger(
        move=ScalingMove.READ_REPLICA,
        observable=ScalingObservable.CONSOLE_READS_IN_FLIGHT,
        basis=ThresholdBasis.FROM_THE_INSTALL,
        unit="connections",
        computed_by="replica_headroom",
        because=(
            "the console and the answer path share the interactive connection pool, so the "
            "number that matters is what is left of that pool once the answer path's own peak "
            "occupancy is accounted for. Both halves are brain.ops.admission's and neither is "
            "a figure this module could state on its own, because the pool depends on how many "
            "slots a worker was given and the occupancy on which capacity profile is installed"
        ),
    ),
    ScalingTrigger(
        move=ScalingMove.MATERIALISED_REPORTS,
        observable=ScalingObservable.REPORT_P95_MS,
        basis=ThresholdBasis.FROM_A_DECLARED_FIGURE,
        unit="ms",
        anchor=REPORT_ANCHOR,
        because=THE_LEAFS_TWO_SECONDS_IS_NOT_DERIVED_FROM_ANYTHING_HERE,
    ),
    ScalingTrigger(
        move=ScalingMove.SPLIT_THE_HOSTS,
        observable=ScalingObservable.PROFILE_DOES_NOT_FIT,
        basis=ThresholdBasis.FROM_A_DECLARED_FIGURE,
        unit="breaches",
        anchor=HOST_ANCHOR,
        because=(
            "the memory half of M36.1.4.3, and it needs no threshold of its own: "
            "brain.ops.wiring already answers whether a profile fits the measured host, and a "
            "second arithmetic here would be a second answer to the question a deployment "
            "decision turns on"
        ),
    ),
    ScalingTrigger(
        move=ScalingMove.SPLIT_THE_HOSTS,
        observable=ScalingObservable.SINGLE_HOST_FAILURE_IS_ACCEPTABLE,
        basis=ThresholdBasis.NOT_ANCHORED,
        unit="a decision",
        because=(
            "the resilience half of M36.1.4.3. It is not a threshold on anything: it is whether "
            "the company installing this accepts that one machine failing takes the whole "
            "system with it, and no measurement in this repository fires it. Recorded as an "
            "open question rather than given a plausible number, because a plausible number "
            "here would make a decision about somebody else's business look like arithmetic"
        ),
    ),
)


def triggers_for(
    move: ScalingMove, triggers: Sequence[ScalingTrigger] | None = None
) -> tuple[ScalingTrigger, ...]:
    """Every trigger declared for one move, in declaration order.

    A tuple rather than one trigger, because a move can be due for more than one reason and
    `SPLIT_THE_HOSTS` is: memory is arithmetic and resilience is a decision. Returning the
    first would silently hide whichever was declared second, and the one that would be hidden
    is the unanchored one, which is exactly the one a reader has to see.
    """
    declared = TRIGGERS if triggers is None else tuple(triggers)
    found = tuple(one for one in declared if one.move is move)
    if not found:
        msg = f"no trigger declares the {move.value} move, so nothing says when it is due"
        raise ScalingError(msg)
    return found


def unanchored(triggers: Sequence[ScalingTrigger] | None = None) -> tuple[ScalingTrigger, ...]:
    """The triggers whose number nobody here can derive.

    The list somebody has to read before believing the table. `brain.locale.triggered` returns
    the deferrals whose trigger has fired; this returns the triggers that have no figure, and
    both exist so an absence is a row rather than a silence.
    """
    declared = TRIGGERS if triggers is None else tuple(triggers)
    return tuple(one for one in declared if one.basis is ThresholdBasis.NOT_ANCHORED)


def trigger_gaps(triggers: Sequence[ScalingTrigger] | None = None) -> tuple[str, ...]:
    """Every way this table has stopped saying when a move is due.

    Three findings. A move nothing declares a trigger for is a move that happens when somebody
    feels like it. An anchor naming this module is a number agreeing with itself, which is what
    made `brain.ops.wiring.HOST_HEADROOM_MIB` wrong for as long as its only test re-derived it.
    And a trigger naming a function this module does not define is a threshold with nothing
    behind it, which reads in the table exactly like one that is computed.
    """
    declared = TRIGGERS if triggers is None else tuple(triggers)
    findings: list[str] = []
    covered = {one.move for one in declared}
    findings.extend(
        f"{move.value}: no trigger, so nothing says when the move becomes due"
        for move in ScalingMove
        if move not in covered
    )
    for one in declared:
        if one.anchor is not None and one.anchor.source.startswith(__name__):
            findings.append(
                f"the {one.move.value} trigger anchors to {one.anchor.source}, which is this "
                "module; an anchor inside the thing it anchors is a number agreeing with itself"
            )
        if one.computed_by and one.computed_by not in globals():
            findings.append(
                f"the {one.move.value} trigger names {one.computed_by!r} as what computes it "
                "and this module defines no such thing, so the threshold has nothing behind it"
            )
    return tuple(findings)


# ---------------------------------------------------------------- the moves, asked directly
def partitioning_is_due(*, retained_window_days: int, interval_days: int) -> bool:
    """Whether a table kept this long is worth cutting into partitions of this size.

    See `PARTITIONING_IS_DUE_AT_CREATION_AND_A_ROW_COUNT_FIRES_LATE`. Both figures are
    arguments rather than read from the constants, because the answer for the metadata ledger
    is yes for every window the retention policy would declare and a function that could only
    ever say yes is a function nobody has watched say no.
    """
    if retained_window_days < 1 or interval_days < 1:
        msg = (
            f"a window of {retained_window_days} day(s) cut into partitions of "
            f"{interval_days} day(s) is not a partitioning question"
        )
        raise ScalingError(msg)
    return retained_window_days > interval_days


def replica_headroom(profile: CapacityProfile, pools: ClassPools) -> int:
    """Console reads the interactive pool has room for once the answer path has its peak.

    Little's law over the profile is the answer path's occupancy at the busiest minute, and
    `brain.ops.admission.little_law_concurrency` is where that arithmetic lives rather than
    being done again here. Rounded up, because half an occupied connection is an occupied one.

    Never negative. A profile whose peak occupancy already exceeds the interactive pool is a
    sizing problem rather than a replica problem, and returning a negative headroom would make
    `replica_is_due` true for zero console reads, which reads as the console being the cause of
    something it is not doing.
    """
    occupied = math.ceil(
        little_law_concurrency(profile.peak_arrivals_per_second, profile.mean_service_seconds)
    )
    return max(0, pools.interactive - occupied)


def replica_is_due(
    profile: CapacityProfile, pools: ClassPools, *, console_reads_in_flight: int
) -> bool:
    """Whether console reads are now taking connections the answer path is sized to need."""
    if console_reads_in_flight < 0:
        msg = f"{console_reads_in_flight} console reads in flight is not a count"
        raise ScalingError(msg)
    return console_reads_in_flight > replica_headroom(profile, pools)


def report_is_due(*, observed_p95_ms: float | None) -> bool:
    """Whether a report is slow enough to be worth materialising.

    None is not due, and that is deliberate rather than a convenience: an unmeasured report is
    not a fast one, but materialising a view is a maintenance obligation and a staleness
    display, and taking one on because nothing measured the report would be paying a permanent
    cost for a reading nobody has. `brain.ops.reliability.attainment` treats an unmeasured
    objective as unmet for the opposite reason and the two are consistent: an unmet objective
    is a finding, and a finding is not the same thing as an instruction to build something.
    """
    return observed_p95_ms is not None and observed_p95_ms > ANSWER_P95_MS


def host_split_is_due(profile: str) -> bool:
    """Whether the profile this install wants fits the measured host. Asked of `wiring`.

    A thin wrapper on purpose. The value is that the trigger and the deployment check are the
    same arithmetic rather than two that agree today, and `HOST_ANCHOR` names the function
    rather than restating its answer.
    """
    return bool(budget_breaches(profile))


# ------------------------------- source fan-out under the estate's ceilings (M36.2.1.3)
def _source_budget(budgets: Sequence[Budget], connector: str) -> Budget:
    """The budget row governing this connector, refusing when nothing does.

    `brain.ops.admission.budget_for` already falls back to the connector-wide default row, so
    the only way to reach the refusal is a budget list with no default at all. It is a refusal
    rather than a zero, because a connector with no ceiling admitted at zero looks like a
    connector that is full, and the two send an operator to opposite places.
    """
    found = budget_for(budgets, (Resource.SOURCE_CALLS, connector))
    if found is None:
        msg = (
            f"no budget row governs source calls to {connector!r} and there is no default row "
            "either, so nothing says how many may be in flight"
        )
        raise ScalingError(msg)
    return found


def implied_global_ceiling(
    budgets: Sequence[Budget], workload: WorkloadClass, *, connectors: Sequence[str]
) -> int:
    """The total source calls that may be in flight, which nobody declared.

    See `NOBODY_DECLARED_A_TOTAL_FOR_SOURCE_CALLS`. The sum of each named connector's
    class-adjusted ceiling, which is what actually binds today. Named as an implication rather
    than as a limit, because a caller reading `global_ceiling` would take it for a decision.
    """
    return sum(
        _source_budget(budgets, connector).ceiling_for(workload)
        for connector in sorted(set(connectors))
    )


def calls_in(plan: FanOutPlan, call_ids: Sequence[str]) -> tuple[SourceCall, ...]:
    """The plan's calls for these ids, in the order the ids were given.

    Refuses an id the plan does not hold rather than skipping it, because a wave computed from
    one plan and costed against another would produce a shorter answer that looks like a
    faster one.
    """
    by_id = {call.call_id: call for call in plan.calls}
    missing = sorted(set(call_ids) - set(by_id))
    if missing:
        msg = f"this plan holds no call(s) {missing}, so a round costed over them would be short"
        raise ScalingError(msg)
    return tuple(by_id[one] for one in call_ids)


def admitted_from(
    calls: Sequence[SourceCall],
    budgets: Sequence[Budget],
    state: CapacityState,
    workload: WorkloadClass,
    *,
    global_ceiling: int | None = None,
) -> tuple[SourceCall, ...]:
    """Which of these calls may start now, per connector and in total (M36.2.1.3).

    Per-connector room is `brain.ops.admission.headroom`, called rather than recomputed, so the
    class ceilings, the seeded limits and this arithmetic cannot disagree. The total is
    `implied_global_ceiling` unless a caller states one, and the parameter exists because an
    install that has declared a total should be able to pass it without this module having
    invented one first.

    Calls are taken in the order the plan declared them. See `THE_CALLERS_ORDER_IS_THE_PRIORITY`.
    """
    connectors = [one.connector for one in calls]
    total = (
        implied_global_ceiling(budgets, workload, connectors=connectors)
        if global_ceiling is None
        else global_ceiling
    )
    if total < 0:
        msg = f"a global ceiling of {total} admits nothing and is not a budget"
        raise ScalingError(msg)
    room = {
        connector: headroom(budgets, state, (Resource.SOURCE_CALLS, connector), workload)
        for connector in set(connectors)
    }
    admitted: list[SourceCall] = []
    for call in calls:
        if len(admitted) >= total:
            break
        if room[call.connector] < 1:
            continue
        room[call.connector] -= 1
        admitted.append(call)
    return tuple(admitted)


def rounds_for(
    calls: Sequence[SourceCall],
    budgets: Sequence[Budget],
    state: CapacityState,
    workload: WorkloadClass,
    *,
    global_ceiling: int | None = None,
) -> int:
    """How many rounds this wave takes before every call in it has started.

    One is what `brain.connectors.federation.FanOutPlan.critical_path_ms` assumes. Anything
    above one is contention, and it is the number this module exists to produce.

    A round that admits nothing raises rather than looping. It means the snapshot already holds
    every slot the wave needs, and returning a round count for a wave that cannot start would
    be a wall clock computed for work nothing is going to do.
    """
    remaining = list(calls)
    rounds = 0
    while remaining:
        admitted = admitted_from(remaining, budgets, state, workload, global_ceiling=global_ceiling)
        if not admitted:
            msg = (
                f"no call in a wave of {len(remaining)} may start, so this wave has no round "
                "count; every connector in it is at its ceiling before the plan begins"
            )
            raise ScalingError(msg)
        rounds += 1
        started = {one.call_id for one in admitted}
        remaining = [one for one in remaining if one.call_id not in started]
    return rounds


def contention_ms(
    plan: FanOutPlan,
    budgets: Sequence[Budget],
    state: CapacityState,
    workload: WorkloadClass,
    *,
    global_ceiling: int | None = None,
) -> int:
    """What the ceilings add to a plan's wall clock, beyond what federation already counts.

    Zero for a plan whose every wave starts at once, which is federation's assumption and is
    the common case on an idle system. Each further round a wave needs costs one more of that
    wave's slowest timeout, because the round runs concurrently and the wave cannot finish
    until its slowest member does.

    Expressed as an addition to `FanOutPlan.critical_path_ms` rather than as a replacement for
    it. A second wall-clock arithmetic over the same plan would be a second answer to how long
    a question takes, and the two would disagree first on exactly the plans nobody tested.
    """
    added = 0
    for wave in plan.waves():
        calls = calls_in(plan, wave)
        extra = rounds_for(calls, budgets, state, workload, global_ceiling=global_ceiling) - 1
        added += extra * max(one.timeout_ms for one in calls)
    return added


def contended_critical_path_ms(
    plan: FanOutPlan,
    budgets: Sequence[Budget],
    state: CapacityState,
    workload: WorkloadClass,
    *,
    global_ceiling: int | None = None,
) -> int:
    """The plan's wall clock once the estate's ceilings are counted (M36.2.1.3).

    `FanOutPlan.critical_path_ms` plus `contention_ms`, and equal to it whenever nothing is
    contended. See `A_WAVE_COSTS_ITS_SLOWEST_MEMBER_ONLY_IF_ALL_OF_IT_CAN_START`.
    """
    return plan.critical_path_ms() + contention_ms(
        plan, budgets, state, workload, global_ceiling=global_ceiling
    )


def fanout_refusals(
    plan: FanOutPlan,
    budgets: Sequence[Budget],
    state: CapacityState,
    workload: WorkloadClass,
    *,
    call_budget: CallBudget | None = None,
    budget_ms: int = FANOUT_BUDGET_MS,
    global_ceiling: int | None = None,
) -> tuple[str, ...]:
    """Every reason this plan cannot be run as planned, per question and per estate.

    Two budgets and neither subsumes the other, which is the distinction
    `brain.connectors.federation.CallBudget` already draws against `brain.ops.limits` and which
    applies again one level out. `CallBudget.check` asks what one question may spend; this asks
    whether the machine has room to spend it at once. A plan can be affordable and still take
    twice its wall clock, and it can be inside its wall clock on an idle system and outside it
    at eleven on a Monday.

    The wall-clock finding is the one worth having. `FanOutPlan.assert_within` passes a plan
    whose critical path fits, and its critical path is computed as though every independent
    call starts together; when the connector ceilings say otherwise it does not, and nothing
    anywhere reported that. See `A_WAVE_COSTS_ITS_SLOWEST_MEMBER_ONLY_IF_ALL_OF_IT_CAN_START`.

    Returns all of them rather than the first, matching `CallBudget.check` itself.
    """
    findings: list[str] = list((call_budget or CallBudget()).check(plan))
    contended = contended_critical_path_ms(
        plan, budgets, state, workload, global_ceiling=global_ceiling
    )
    if contended > budget_ms:
        findings.append(
            f"this plan's critical path is {plan.critical_path_ms()}ms on an idle system and "
            f"{contended}ms against the {workload.value} class's share of the connector "
            f"ceilings, which is over the {budget_ms}ms fan-out budget. "
            f"{A_WAVE_COSTS_ITS_SLOWEST_MEMBER_ONLY_IF_ALL_OF_IT_CAN_START}"
        )
    return tuple(findings)


def scaling_gaps(budgets: Sequence[Budget], workload: WorkloadClass) -> tuple[str, ...]:
    """What the budget declaration does not say about running source calls in parallel.

    One finding today and it is a real one: `Resource.SOURCE_CALLS` is in
    `brain.ops.admission.PER_CONNECTOR`, so every row it can have is keyed and a global row is
    refused at construction. The total in flight is therefore an addition rather than a
    decision. Reported with the number it comes to, because "no total is declared" is easy to
    read past and "twenty-one calls may be in flight and nobody chose twenty-one" is not.

    Empty for a budget list with no per-connector source rows in it, which is the only way this
    can be quiet: there is nothing to add up, so nothing has been decided by addition.
    """
    findings: list[str] = []
    keyed = sorted({b.key for b in budgets if b.resource is Resource.SOURCE_CALLS and b.key})
    if keyed:
        total = implied_global_ceiling(budgets, workload, connectors=keyed)
        findings.append(
            f"source calls have {len(keyed)} per-connector row(s) and no global row, so up to "
            f"{total} may be in flight at once for the {workload.value} class and nobody chose "
            f"that figure. {NOBODY_DECLARED_A_TOTAL_FOR_SOURCE_CALLS}"
        )
    return tuple(findings)


# ------------------------------------------- sharing one answer execution (M36.2.3)
def may_share(waiting: CacheKeyParts, running: CacheKeyParts) -> bool:
    """Whether a request may be attached to an answer already being computed.

    **The rule is `brain.gate.cache_key.cache_key` and there is no second one.** See
    `A_SHARED_EXECUTION_IS_A_CACHE_ENTRY_THAT_HAS_NOT_FINISHED_YET`: two callers who may be
    served one cached answer are exactly the two who may be served one in-flight execution, so
    the comparison is the key that already decides the first question rather than a set of
    fields chosen here. That key length-prefixes its parts so no two different part lists
    collide, and it refuses an empty entitlement hash outright with the argument this leaf is
    about.

    Volatile questions are refused. See
    `A_QUESTION_TOO_VOLATILE_TO_CACHE_IS_TOO_VOLATILE_TO_SHARE`.
    """
    if volatile(waiting) or volatile(running):
        return False
    return cache_key(waiting) == cache_key(running)


def volatile(parts: CacheKeyParts) -> bool:
    """Whether this question's shape or sources put it outside the cache.

    `brain.gate.cache_key.is_volatile` asked of the parts, so the sharing decision and the
    caching decision consult one predicate. The sources are the names the key already carries,
    which is what makes this answerable from the parts alone.
    """
    return is_volatile(parts.question, frozenset(parts.source_epochs))


def share_role(waiting: CacheKeyParts, running: CacheKeyParts) -> FlightRole:
    """Whether this caller waits for the run in flight or performs its own.

    `brain.connectors.federation.FlightRole` rather than a second pair of names, because a
    reader who has learnt what a leader and a follower are at the fetch layer should not have
    to learn two more words for the same two positions one layer out.
    """
    return FlightRole.FOLLOWER if may_share(waiting, running) else FlightRole.LEADER


def share_refusals(waiting: CacheKeyParts, running: CacheKeyParts) -> tuple[str, ...]:
    """Which parts differ, named without their values.

    See `A_SHARE_REFUSAL_NAMES_THE_FIELD_AND_NEVER_THE_VALUES`. Every differing part rather
    than the first, so an operator sees whether two requests missed by one part or by all of
    them, and the two mean different things: one part is a near miss worth understanding and
    all of them is two unrelated requests that happened to arrive together.

    Volatility is reported as its own finding rather than as a differing field, because two
    identical volatile questions differ in nothing at all and still may not share.
    """
    findings: list[str] = [
        f"{one.name} differs, so these are not the same question under the same reach"
        for one in fields(waiting)
        if getattr(waiting, one.name) != getattr(running, one.name)
    ]
    if volatile(waiting) or volatile(running):
        findings.append(
            "one of these is too volatile to cache, so it is too volatile to share. "
            f"{A_QUESTION_TOO_VOLATILE_TO_CACHE_IS_TOO_VOLATILE_TO_SHARE}"
        )
    return tuple(findings)


#: Field names on a sharing key that would turn equality into similarity.
#:
#: Scanned for rather than trusted, because the way this rule dies is one field added to make
#: coalescing hit more often, and the person adding it will be looking at a hit rate. The
#: construction is `brain.ops.retention._OVERRIDE_NAMES`.
_SIMILARITY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "close_enough",
        "department",
        "distance",
        "ent_prefix",
        "fuzzy",
        "role",
        "similarity",
        "threshold",
        "tolerance",
    }
)


def coalescing_gaps(model: type = CacheKeyParts) -> tuple[str, ...]:
    """Every way the sharing key has stopped requiring an equal reach.

    Two findings. A field whose name admits a tolerance is similarity arriving as a column, and
    a key that has lost the entitlement hash altogether is two requests shared on the question
    alone, which is the same failure with nothing left to compare.

    **Pointed at another module's type on purpose.** The key belongs to `brain.gate.cache_key`
    because caching decided it first, and this is the check that it keeps being the thing this
    leaf needs it to be: an edit made for a cache hit rate would arrive there, and a scan that
    only ever looked at a type declared here would never see it.

    `model` is a parameter defaulting to that type for the reason
    `brain.ops.retention.retention_policy_gaps` takes one: a scan that can only ever be pointed
    at a type known to be clean is a scan nobody has seen produce a finding.
    """
    findings: list[str] = []
    names = {one.name for one in fields(model)}
    findings.extend(
        f"{model.__name__} carries {name!r}, which is a tolerance on a comparison that has to "
        f"be equality. {SIMILAR_REACH_IS_NOT_EQUAL_REACH}"
        for name in sorted(names & _SIMILARITY_NAMES)
    )
    if "ent_hash" not in names:
        findings.append(
            f"{model.__name__} carries no entitlement hash, so two requests would share an "
            "execution on the question alone and whichever ran first would decide what the "
            "other one was allowed to see"
        )
    return tuple(findings)


#: What the parallelism half of M36.2 is measured against, said rather than restated.
#:
#: M36.2.4 asks for a peak-concurrency test, a documented first bottleneck at ten and a hundred
#: times, and results recorded against the SLO table. All three exist already:
#: `brain.ops.admission.LOAD_TEST_TARGET` is the peak-concurrency specification,
#: `brain.ops.admission.bottleneck_ladder` and `FIRST_BOTTLENECK_AT_SCALE` are the ladder, and
#: `brain.ops.reliability.LANE_OBJECTIVES` with `attainment` is the SLO table and the comparison
#: against it. Those are M22.3.1, M22.3.3, M22.3.4 and M30.5.1, which is the same work with
#: different task ids, so nothing here reimplements any of it.
M36_2_4_IS_ALREADY_M22_3_AND_M30_5: Final = (
    "The peak concurrency target is brain.ops.admission.LOAD_TEST_TARGET, the first bottleneck "
    "at ten and a hundred times is bottleneck_ladder and FIRST_BOTTLENECK_AT_SCALE in the same "
    "module, and the SLO table results are recorded against is "
    "brain.ops.reliability.LANE_OBJECTIVES through attainment. Building any of them again here "
    "would put a second answer to each in one repository, and the second copy is the one that "
    "would be wrong in production. What is genuinely missing is the run itself, which needs a "
    "deployed system to drive and is not domain logic."
)
