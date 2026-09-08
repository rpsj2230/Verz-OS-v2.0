"""Whether to split a run into children, decided by arithmetic and defaulting to no.

Architecture section 14: "a gate decides in pure arithmetic whether parallel beats serial.
Fail any condition and the run collapses to a single loop, which is the default rather than
the exception." Every word of that is load-bearing and this module is each of them in turn.

**Pure arithmetic**, which means no model is asked and nothing here reads a value the thing
being gated produced. `brain.orchestration.plan` is where that is enforced: a proposal
carries structure and never a weight, so the six numbers below come from the estimator the
budget is sized against and from whoever measured the coupling. A gate whose inputs the
planner could write is a gate the planner passes.

**Six conditions, evaluated before any child starts.** They are dispatched by an exhaustive
`match` over `Condition` with `assert_never`, so a seventh cannot reach production without
somebody writing its arithmetic, and a mapping with a default would admit one silently as
whatever the default happened to be. `brain.gate.leash.route_for` makes the same argument
about a fourth autonomy tier. Each condition is tested with a plan on which it is the only
one failing, because six conditions of which two are unreachable is four conditions and a
paragraph.

**The default is the single loop and it is not the absence of a verdict.** This is the part
that is easy to build wrongly. Returning parallel when nothing failed makes the default an
accident of the condition list: delete all six and every plan fans out, and the deletion
looks like a simplification. So `GateRecord` refuses to hold a parallel verdict unless it
also holds the full `CONDITION_ORDER` as the conditions evaluated, and `decide` builds the
record rather than returning a bare enum. A gate with a condition missing cannot produce a
record saying parallel, whatever its arithmetic concluded. See
`SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH`.

**Where the numbers come from.** Two of the six ceilings are not chosen here at all and the
other two are derived rather than picked.

`MAX_COST_MULTIPLIER` is 1.4, which is the *low* end of the published measurement of naive
fan-out, and the point of putting it there is that a plan is admitted only when it is
cheaper than the cheapest naive split anybody has measured. The prior system measured 2.15,
so the figure to beat is not close. `MIN_SPEEDUP` is 2.0 and is pinned against the cost
ceiling rather than chosen beside it: a fan-out that multiplies spend by 1.4 has to save
more than 1.4 times the latency or it is a worse answer at a higher price, so the test
asserts `MIN_SPEEDUP > MAX_COST_MULTIPLIER` and the relation is what makes both figures
defensible. `MAX_LARGEST_SHARE` is not a figure at all: it is `1 / MIN_BRANCHES`, the even
share at the minimum branch count, so a plan whose largest subtask is bigger than that is
one subtask with decoration around it. And the concurrency and depth ceilings are
`brain.orchestration.delegation`'s, imported rather than restated, because the gate's answer
and the delegation cap have to be the same number or a plan passes the gate and its children
are refused one at a time.

**Speedup and dominance are two conditions on purpose.** They agree whenever duration is
proportional to cost, and the case they disagree in is the one worth guarding: an optimistic
duration estimate. A plan whose largest branch is nine tenths of the estimated cost and
whose durations claim otherwise passes the speedup condition and fails this one, and the
duration estimate is the softer of the two numbers because it is the one that depends on
what a connector does today.

**Nothing here records who asked or what about.** `GateRecord` carries a run id, six
numbers, the conditions and the verdict. There is no field for the question, the subtask
objectives or the caller, which is `brain.ops.tracing`'s rule for a span applied to a gate
decision: an audit row that quoted the plan would be a copy of somebody's question with a
different retention on it. `gate_record_gaps` asks that of the type rather than leaving it
to review.

Rejected: a score. Weighting six conditions into one number and comparing it against a
threshold is the arrangement in which a plan that fails a condition badly can be carried by
five it passes narrowly, and the tuning of the weights becomes the real policy. Every
condition here is a veto, which is also what "fail any condition" says.

Rejected: an override for a plan an operator believes in. It is the fifth branch
`brain.ops.admission.decide` refuses for the same reason: a gate with an exception is a
gate that binds on the days nothing was going to go wrong.

Rejected: making the gate advisory and letting the runtime decide. There is no runtime, so
an advisory gate would be a calculation nobody consults, and by the time there is one the
advice will be the thing that is switched off during an incident.

Task ids: M18.2.2, M18.2.3, M18.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, assert_never

from brain.orchestration.delegation import MAX_CHILDREN_PER_RUN, MAX_DELEGATION_DEPTH
from brain.orchestration.plan import DependencyGraph

# ------------------------------------------------------------------ written-down reasons
#: Why the collapse is a construction rather than an else branch.
SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH: Final = (
    "A gate that returns parallel when nothing failed makes the default an accident of the "
    "condition list: delete every condition and every plan fans out, and the deletion reads "
    "in a diff as a simplification. So the verdict is carried in a record that refuses to "
    "say parallel unless it also names the whole of CONDITION_ORDER as what it evaluated. A "
    "gate with a condition missing cannot produce a parallel record whatever its arithmetic "
    "concluded, which is the difference between a default and a fallthrough."
)

#: Why the published measurements set the cost ceiling rather than a round number.
THE_CEILING_IS_THE_CHEAPEST_MEASURED_NAIVE_SPLIT: Final = (
    "Published measurements put naive fan-out at 1.4 to 1.6 times the cost for gains at the "
    "level of noise, and the prior system this replaces measured 2.15. Setting the ceiling "
    "at the low end of that range means a plan is admitted only when it is cheaper than the "
    "cheapest naive split anybody has measured, which is the only reading of the number "
    "that makes the gate worth having: a ceiling above it would admit exactly the splits "
    "the measurements say are not worth making."
)

#: Why an audit row for a gate decision holds numbers and nothing else.
A_GATE_RECORD_IS_NUMBERS_AND_NEVER_A_QUESTION: Final = (
    "brain.ops.tracing keeps payloads out of spans because a span is read by an operator "
    "who wanted the shape, the outcome and the latency and never wanted the question. A "
    "gate record is the same object at a different scale: it exists so somebody can ask "
    "afterwards why a run did or did not split, and the six numbers answer that completely. "
    "A field holding the question, or the subtask objectives, would be a copy of somebody's "
    "data on an operational surface with its own retention, which is what brain.ops.jobs."
    "DeadLetter refuses for the same reason."
)


class FanOutError(Exception):
    """A gate record or a dispatch that cannot mean what it says.

    Outside the `brain.core.errors` taxonomy, like the rest of this package: nobody asking a
    question ever sees one.
    """


# --------------------------------------------------------------------------- the ceilings
#: The fewest branches worth splitting into. One branch is a single loop with machinery
#: around it, and the machinery is the part that costs.
MIN_BRANCHES: Final = 2

#: The low end of the published measurement of naive fan-out, and the prior system's own
#: figure. Carried as constants so the ceiling below can be asserted against them rather
#: than against itself, which is what `brain.connectors.hubspot.CEILING_NAME` learned to do
#: after a mutation repointed a constant and every test that read it moved with it.
NAIVE_FAN_OUT_MEASURED_LOW: Final = 1.4
NAIVE_FAN_OUT_PRIOR_SYSTEM: Final = 2.15

#: The most a fan-out may multiply the spend by. See
#: `THE_CEILING_IS_THE_CHEAPEST_MEASURED_NAIVE_SPLIT`.
MAX_COST_MULTIPLIER: Final = NAIVE_FAN_OUT_MEASURED_LOW

#: The least a fan-out must divide the latency by. Above `MAX_COST_MULTIPLIER`, because a
#: split that costs 1.4 times as much and saves less than 1.4 times the wait is a worse
#: answer at a higher price, and the relation rather than the figure is what a test pins.
MIN_SPEEDUP: Final = 2.0

#: The most of a plan's estimated cost one subtask may be. Derived rather than chosen: at
#: the minimum branch count an even split gives each branch this much, so a subtask above it
#: is a plan that is one piece of work with decoration around it.
MAX_LARGEST_SHARE: Final = 1.0 / MIN_BRANCHES


class Condition(enum.StrEnum):
    """The six things that must all be true before a run splits.

    Six, and each one prevents a failure the other five do not see. A member here earns its
    place by having a plan on which it is the only condition failing, which is what the test
    suite asserts one at a time: six conditions of which two are unreachable is four
    conditions and a paragraph.
    """

    #: There is more than one thing that could start at once.
    ENOUGH_BRANCHES = "enough_branches"
    #: There are not more than one run may have in flight.
    WITHIN_RUN_CONCURRENCY = "within_run_concurrency"
    #: The children would sit inside the delegation depth cap.
    WITHIN_DEPTH = "within_depth"
    #: The duplicated context keeps the spend inside the measured ceiling.
    COST_MULTIPLIER_BOUNDED = "cost_multiplier_bounded"
    #: The critical path is enough shorter than the sum to pay for the multiplier.
    SPEEDUP_WORTH_IT = "speedup_worth_it"
    #: No single subtask is most of the plan.
    NO_BRANCH_DOMINATES = "no_branch_dominates"


#: The order the conditions are evaluated and recorded in, written out rather than taken
#: from the enum's declaration order, for the reason `brain.gate.leash.CHECK_ORDER` is
#: written out: declaration order is not part of an enum's contract and a reordering during
#: a merge would silently change what a record means.
#:
#: The order is cheapest first and it is also meaning: the three structural conditions ask
#: whether there is anything to split and whether the split would be allowed to run, and the
#: three economic ones ask whether it is worth doing. A record whose failures are all
#: structural is a plan shaped wrongly; one whose failures are economic is a plan that is
#: fine and not worth splitting, and those send a reader to different places.
CONDITION_ORDER: Final[tuple[Condition, ...]] = (
    Condition.ENOUGH_BRANCHES,
    Condition.WITHIN_RUN_CONCURRENCY,
    Condition.WITHIN_DEPTH,
    Condition.COST_MULTIPLIER_BOUNDED,
    Condition.SPEEDUP_WORTH_IT,
    Condition.NO_BRANCH_DOMINATES,
)

#: How many conditions there are, as the work breakdown names it. Stated as a constant so
#: that adding a seventh without arguing for it fails a test rather than passing quietly.
HOW_MANY_CONDITIONS: Final = 6


class Verdict(enum.StrEnum):
    """What the gate decided. Two members and no third, because there is no maybe.

    `SINGLE_LOOP` is not a refusal and nothing about it is degraded: it is the default way a
    run happens, and the whole plan still executes. Naming it as a verdict rather than as
    the absence of one is deliberate, so a record always says what was decided.
    """

    SINGLE_LOOP = "single_loop"
    PARALLEL = "parallel"


# ------------------------------------------------------------------ the inputs (M18.2.4)
@dataclass(frozen=True)
class GateInputs:
    """The six numbers the conditions are evaluated over, and nothing else.

    Read off the graph by `gate_inputs` rather than passed in by a caller, so the record and
    the decision cannot be computed from different figures. There is no field here for the
    question, the objectives or the asker; see
    `A_GATE_RECORD_IS_NUMBERS_AND_NEVER_A_QUESTION`.
    """

    #: How many subtasks could start at once. The first wave, not the node count.
    branches: int
    #: How many delegations deep the run already is. The children would be one deeper.
    depth: int
    cost_multiplier: float
    speedup: float
    largest_share: float

    def __post_init__(self) -> None:
        if self.branches < 0 or self.depth < 0:
            msg = f"a plan cannot have {self.branches} branches at depth {self.depth}"
            raise FanOutError(msg)


def gate_inputs(graph: DependencyGraph, *, depth: int) -> GateInputs:
    """The numbers, read off the weighted graph and the run's current depth.

    `depth` is the only argument that is not the graph's, because a plan does not know where
    in a chain it sits: the same decomposition is worth splitting at depth zero and refused
    at the cap, and that is a property of the run rather than of the work.
    """
    return GateInputs(
        branches=len(graph.frontier()),
        depth=depth,
        cost_multiplier=graph.cost_multiplier,
        speedup=graph.speedup,
        largest_share=graph.largest_share,
    )


def holds(condition: Condition, inputs: GateInputs) -> bool:
    """Whether one condition is satisfied. Exhaustive, so a seventh is a type error.

    Every branch is a comparison and there is no call in here at all, which is what "pure
    arithmetic" means and is worth being able to see in one screen. A condition that had to
    look something up would be a condition whose answer depended on when it was asked.
    """
    match condition:
        case Condition.ENOUGH_BRANCHES:
            return inputs.branches >= MIN_BRANCHES
        case Condition.WITHIN_RUN_CONCURRENCY:
            return inputs.branches <= MAX_CHILDREN_PER_RUN
        case Condition.WITHIN_DEPTH:
            return inputs.depth + 1 <= MAX_DELEGATION_DEPTH
        case Condition.COST_MULTIPLIER_BOUNDED:
            return inputs.cost_multiplier <= MAX_COST_MULTIPLIER
        case Condition.SPEEDUP_WORTH_IT:
            return inputs.speedup >= MIN_SPEEDUP
        case Condition.NO_BRANCH_DOMINATES:
            return inputs.largest_share <= MAX_LARGEST_SHARE
        case _:
            assert_never(condition)


def failures(
    inputs: GateInputs, order: Sequence[Condition] = CONDITION_ORDER
) -> tuple[Condition, ...]:
    """Every condition this plan fails, in `CONDITION_ORDER`.

    All of them rather than the first, and that is not the usual argument about a caller
    learning once. It is that a plan failing one economic condition is worth reshaping and a
    plan failing four is not, and a gate that short-circuited would report the first failure
    on both and send somebody to tune a coupling weight that was never the problem.

    `order` is a parameter with a default for the reason `brain.ops.queue.concurrency_gaps`
    takes one: a check that can only be run against the constant beside it cannot be shown
    to fail, and a check nobody has seen fail is a check nobody knows works.
    """
    return tuple(condition for condition in order if not holds(condition, inputs))


# ------------------------------------------------------------------ the record (M18.2.4)
@dataclass(frozen=True)
class GateRecord:
    """What the gate was given, what it evaluated, and what it decided (M18.2.4).

    The constructor is where M18.2.3 stops being a sentence. A record may say `PARALLEL`
    only when it names no failed condition *and* names the whole of `CONDITION_ORDER` as
    what it evaluated, so a gate that skipped a condition cannot produce a parallel verdict
    however its arithmetic came out. See
    `SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH`.

    `evaluated` is carried rather than assumed for the same reason
    `brain.gate.leash.Decision.checks` is: an auditor asking whether all six ran needs the
    answer in the row, not in the source of the version that wrote it.
    """

    run_id: str
    at: datetime
    inputs: GateInputs
    #: The conditions actually evaluated, in order.
    evaluated: tuple[Condition, ...]
    #: Those of them that did not hold.
    failed: tuple[Condition, ...]
    verdict: Verdict

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "a gate record naming no run cannot be found again by anybody asking why"
            raise FanOutError(msg)
        if self.at.tzinfo is None:
            msg = (
                f"the gate record for {self.run_id!r} is dated with no timezone, so two "
                "records from two hosts cannot be put in order"
            )
            raise FanOutError(msg)
        outside = sorted(set(self.failed) - set(self.evaluated))
        if outside:
            msg = (
                f"the record for {self.run_id!r} reports {outside} as failed and does not "
                "list them as evaluated, so it says a condition it never asked came out no"
            )
            raise FanOutError(msg)
        if self.verdict is not Verdict.PARALLEL:
            return
        if self.failed:
            msg = (
                f"the record for {self.run_id!r} says {self.verdict} with {list(self.failed)} "
                f"failed. {SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH}"
            )
            raise FanOutError(msg)
        if tuple(self.evaluated) != CONDITION_ORDER:
            msg = (
                f"the record for {self.run_id!r} says {self.verdict} having evaluated "
                f"{list(self.evaluated)} rather than all {HOW_MANY_CONDITIONS} conditions. "
                f"{SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH}"
            )
            raise FanOutError(msg)

    @property
    def parallel(self) -> bool:
        return self.verdict is Verdict.PARALLEL


def decide(
    run_id: str,
    graph: DependencyGraph,
    *,
    depth: int,
    at: datetime,
    order: Sequence[Condition] = CONDITION_ORDER,
) -> GateRecord:
    """Evaluate all six conditions and record the verdict, before any child starts (M18.2.2).

    The record is the return value rather than the verdict, because the leaf asks for the
    inputs and the verdict to be recorded for audit and a function returning only the
    verdict would leave the recording to a caller who may not do it. This is
    `brain.gate.leash.govern`'s arrangement: one entry point, so there is a single place to
    read for the answer to "why did this run split".

    `order` is passed through to `failures` and is what makes the constructor's refusal
    reachable: called with fewer than six conditions, this produces a record that would say
    parallel and is refused for saying it. That is the test of
    `SINGLE_LOOP_IS_THE_DEFAULT_AND_NOT_A_FALLTHROUGH`, and without the parameter there
    would be no way to reach it.
    """
    inputs = gate_inputs(graph, depth=depth)
    failed = failures(inputs, order)
    return GateRecord(
        run_id=run_id,
        at=at,
        inputs=inputs,
        evaluated=tuple(order),
        failed=failed,
        verdict=Verdict.SINGLE_LOOP if failed else Verdict.PARALLEL,
    )


def dispatch_refusals(record: GateRecord, children: Sequence[str]) -> tuple[str, ...]:
    """Every reason these children may not start, given what the gate decided (M18.2.2).

    The leaf says the conditions are evaluated *before any child starts*, and nothing in a
    repository with no runtime can prove when something happened. What it can do is make the
    gate record an input to dispatch, so that starting children without one is not
    expressible: this function has no default for `record`, and a caller with no record has
    nothing to pass.

    Refuses more children than the frontier as well as a single-loop verdict. A plan gated
    on four branches and dispatched as six is a plan two of whose children were never
    weighed, and the gate's arithmetic was done over a different run from the one about to
    happen.
    """
    findings: list[str] = []
    if not record.parallel:
        findings.append(
            f"the gate decided {record.verdict} for run {record.run_id!r} because "
            f"{[str(one) for one in record.failed]} did not hold, so there are no children "
            "to start and the plan runs as one loop"
        )
    if len(children) > record.inputs.branches:
        findings.append(
            f"run {record.run_id!r} would start {len(children)} children and the gate was "
            f"asked about {record.inputs.branches}; the arithmetic was done over a smaller "
            "plan than the one about to run"
        )
    duplicated = sorted({one for one in children if list(children).count(one) > 1})
    findings.extend(
        f"child {one!r} would be started twice by run {record.run_id!r}, which is one "
        "subtask counted once by the gate and dispatched twice"
        for one in duplicated
    )
    return tuple(findings)


# ------------------------------------------------------------------------- the diagnostic
#: Field names that would put somebody's question on a gate record. Names rather than a rule
#: about values, because the failure arrives as a field somebody adds to make an audit row
#: more useful, and it arrives with one of these names on it. See
#: `A_GATE_RECORD_IS_NUMBERS_AND_NEVER_A_QUESTION`.
NAMES_THAT_WOULD_BE_A_PAYLOAD: Final[frozenset[str]] = frozenset(
    {
        "question",
        "objective",
        "objectives",
        "prompt",
        "answer",
        "principal_id",
        "asker",
        "text",
        "detail",
    }
)

#: The types an auditor reads. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`: a type added to this surface and not to this tuple is
#: a type the check below never sees.
AUDIT_SURFACE: Final[tuple[type, ...]] = (GateInputs, GateRecord)


def gate_record_gaps(surface: Sequence[type] = AUDIT_SURFACE) -> tuple[str, ...]:
    """Fields on the audit surface that would carry a payload rather than a number.

    A check rather than a paragraph, for the reason `brain.ops.jobs.hidden_count_fields` is
    one: a rule that lives only in prose is defeated by somebody adding one field, and the
    field will be added by somebody making an audit row more useful. Reported as
    `Type.field` so the finding names the edit.
    """
    findings: list[str] = []
    for record_type in surface:
        declared: Mapping[str, Any] = getattr(record_type, "__dataclass_fields__", {})
        findings.extend(
            f"{record_type.__name__}.{name}"
            for name in declared
            if name in NAMES_THAT_WOULD_BE_A_PAYLOAD
        )
    return tuple(findings)
