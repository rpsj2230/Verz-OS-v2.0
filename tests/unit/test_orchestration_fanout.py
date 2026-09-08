"""Six conditions, each with a plan on which it is the only one failing, and a default of no.

Two properties carry this file.

**Six conditions of which two are unreachable is four conditions and a paragraph.** So each
one is tested against inputs on which it alone fails, and the set of failures is asserted
rather than the verdict, because a verdict of single loop is produced by any failure at all
and would report five conditions as working when one was.

**The collapse is a construction and not an else branch.** The test that matters most here
is the one that deletes conditions: a gate that returned parallel whenever nothing failed
would fan out every plan the moment the condition list was emptied, and the record refuses
to say parallel unless it also names all six as evaluated.

The per-condition tests build `GateInputs` directly, because that is what `holds` reads.
The tests either side of them drive `decide` from a real `DependencyGraph`, so the numbers
`gate_inputs` produces are checked against the graph that produced them rather than against
a set of inputs written to match: a producer and a consumer on either side of one value
need a test written from the producer's own output or there are two tests for the consumer.

Task ids: M18.2.2, M18.2.3, M18.2.4
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from brain.core.lane import Lane
from brain.models.routing import Tier
from brain.ops.spend import CostInputs
from brain.orchestration.delegation import MAX_CHILDREN_PER_RUN, MAX_DELEGATION_DEPTH
from brain.orchestration.fanout import (
    CONDITION_ORDER,
    HOW_MANY_CONDITIONS,
    MAX_COST_MULTIPLIER,
    MAX_LARGEST_SHARE,
    MIN_BRANCHES,
    MIN_SPEEDUP,
    NAIVE_FAN_OUT_MEASURED_LOW,
    NAIVE_FAN_OUT_PRIOR_SYSTEM,
    Condition,
    FanOutError,
    GateInputs,
    GateRecord,
    Verdict,
    decide,
    dispatch_refusals,
    failures,
    gate_inputs,
    gate_record_gaps,
    holds,
)
from brain.orchestration.plan import DependencyGraph, Edge, Node

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)


def _inputs(**overrides: object) -> GateInputs:
    """Inputs that pass every condition, so a test can fail exactly one of them."""
    fields: dict[str, object] = {
        "branches": 3,
        "depth": 0,
        "cost_multiplier": 1.1,
        "speedup": 2.5,
        "largest_share": 0.4,
    }
    fields.update(overrides)
    return GateInputs(**fields)  # type: ignore[arg-type]


def _node(subtask_id: str, *, retrieval_tokens: int, seconds: float) -> Node:
    return Node(
        subtask_id=subtask_id,
        cost=CostInputs(
            lane=Lane.TASK, tier=Tier.MAIN, tool_calls=1, retrieval_tokens=retrieval_tokens
        ),
        seconds=seconds,
    )


def _splittable() -> DependencyGraph:
    """Three even, independent branches feeding one small merge step.

    Even, because the dominance condition is about one branch being most of the plan; long
    beside the merge step, because the speedup condition needs the sum to be well above the
    critical path; and lightly coupled, because the cost condition is about what a split
    duplicates. Every one of the six holds, which is what makes it the fixture for the
    positive case.
    """
    return DependencyGraph(
        nodes=(
            _node("s-1", retrieval_tokens=3_000, seconds=20.0),
            _node("s-2", retrieval_tokens=3_000, seconds=20.0),
            _node("s-3", retrieval_tokens=3_000, seconds=20.0),
            _node("s-4", retrieval_tokens=200, seconds=2.0),
        ),
        edges=(
            Edge(before="s-1", after="s-4", coupling_tokens=100),
            Edge(before="s-2", after="s-4", coupling_tokens=100),
            Edge(before="s-3", after="s-4", coupling_tokens=100),
        ),
    )


# ------------------------------------------------------------------------ the six
def test_there_are_six_conditions_and_the_order_names_every_one_of_them():
    """The work breakdown asks for six. Pinned as a count and as a set, so a seventh added
    without an argument fails here and a member left out of `CONDITION_ORDER` fails too.

    Delete this and a condition could be dropped from the order and never evaluated, which
    the record's own check would then be satisfied by, because it compares against the
    order rather than against the enum."""
    assert len(Condition) == HOW_MANY_CONDITIONS
    assert set(CONDITION_ORDER) == set(Condition)
    assert len(CONDITION_ORDER) == HOW_MANY_CONDITIONS


@pytest.mark.parametrize(
    ("condition", "overrides"),
    [
        (Condition.ENOUGH_BRANCHES, {"branches": 1}),
        (Condition.WITHIN_RUN_CONCURRENCY, {"branches": MAX_CHILDREN_PER_RUN + 1}),
        (Condition.WITHIN_DEPTH, {"depth": MAX_DELEGATION_DEPTH}),
        (Condition.COST_MULTIPLIER_BOUNDED, {"cost_multiplier": MAX_COST_MULTIPLIER + 0.01}),
        (Condition.SPEEDUP_WORTH_IT, {"speedup": MIN_SPEEDUP - 0.01}),
        (Condition.NO_BRANCH_DOMINATES, {"largest_share": MAX_LARGEST_SHARE + 0.01}),
    ],
)
def test_each_condition_has_a_plan_on_which_it_is_the_only_one_failing(condition, overrides):
    """**This is what makes six conditions six rather than four and a paragraph.**

    Each row breaks exactly one condition against a set of inputs that otherwise passes, and
    asserts the whole failure set rather than the verdict: any failure produces a single
    loop, so asserting the verdict would report five working conditions as six.

    Delete this and a condition could become unreachable, always true, or a duplicate of
    another, and every other test in this file would still pass."""
    broken = _inputs(**overrides)

    assert failures(broken) == (condition,)
    assert not holds(condition, broken)
    assert holds(condition, _inputs())


def test_inputs_that_pass_every_condition_fail_none():
    """The positive half of the parametrised test above, stated once. A condition set tested
    only by its failures is satisfied by conditions that all return False.

    Delete this and `holds` could return False for everything, and the gate would collapse
    every plan to a single loop while every refusal test passed."""
    assert failures(_inputs()) == ()


def test_the_boundary_of_every_numeric_condition_is_inclusive():
    """A boundary tested only from outside is a boundary that can move by one without
    failing, and the direction nobody notices is the permissive one.

    Delete this and each of the four ceilings could be off by one, which changes how many
    plans fan out without changing any constant."""
    assert holds(Condition.ENOUGH_BRANCHES, _inputs(branches=MIN_BRANCHES))
    assert holds(Condition.WITHIN_RUN_CONCURRENCY, _inputs(branches=MAX_CHILDREN_PER_RUN))
    assert holds(Condition.WITHIN_DEPTH, _inputs(depth=MAX_DELEGATION_DEPTH - 1))
    assert holds(Condition.COST_MULTIPLIER_BOUNDED, _inputs(cost_multiplier=MAX_COST_MULTIPLIER))
    assert holds(Condition.SPEEDUP_WORTH_IT, _inputs(speedup=MIN_SPEEDUP))
    assert holds(Condition.NO_BRANCH_DOMINATES, _inputs(largest_share=MAX_LARGEST_SHARE))


def test_speedup_and_dominance_disagree_when_the_duration_estimate_is_optimistic():
    """The case that makes them two conditions rather than one.

    Whenever duration is proportional to cost they agree, so the only way to justify both is
    to show the plan on which they part: one branch that is most of the estimated cost, with
    durations claiming otherwise. The duration estimate is the softer number because it
    depends on what a connector does today.

    Delete this and somebody tidying the gate would notice the two conditions usually agree
    and remove one, and it would be the one that does not depend on a guess."""
    optimistic = _inputs(largest_share=0.9, speedup=3.0)

    assert holds(Condition.SPEEDUP_WORTH_IT, optimistic)
    assert not holds(Condition.NO_BRANCH_DOMINATES, optimistic)
    assert failures(optimistic) == (Condition.NO_BRANCH_DOMINATES,)


# ------------------------------------------------------------------ where the numbers come from
def test_the_cost_ceiling_is_at_or_below_the_cheapest_measured_naive_split():
    """Asserted against the measurements rather than against itself, which is the lesson
    `hubspot.CEILING_NAME` cost: a test comparing a constant against the constant it imports
    is green for every value it could hold.

    Delete this and the ceiling could be raised to two, which admits exactly the splits the
    published measurements say are not worth making."""
    assert MAX_COST_MULTIPLIER <= NAIVE_FAN_OUT_MEASURED_LOW
    assert NAIVE_FAN_OUT_MEASURED_LOW < NAIVE_FAN_OUT_PRIOR_SYSTEM


def test_the_speedup_floor_is_above_the_cost_ceiling():
    """A split that multiplies spend by 1.4 has to save more than 1.4 times the wait, or it
    is a worse answer at a higher price. The relation is the argument; the figures are
    where the relation happens to sit.

    Delete this and either constant could move independently, and the gate would admit
    splits that cost more than they save while both numbers still looked defensible."""
    assert MIN_SPEEDUP > MAX_COST_MULTIPLIER


def test_the_dominance_ceiling_is_the_even_share_at_the_minimum_branch_count():
    """Derived rather than chosen: at the fewest branches worth splitting into, an even
    split gives each branch this much.

    Delete this and `MAX_LARGEST_SHARE` becomes a free number, and raising it would admit
    plans that are one piece of work with decoration around it."""
    assert MAX_LARGEST_SHARE == 1.0 / MIN_BRANCHES


def test_the_concurrency_and_depth_ceilings_are_delegations_own():
    """The gate's answer and the delegation caps have to be the same numbers, or a plan
    passes the gate and its children are refused one at a time.

    Delete this and this module could grow its own copies, and the copy that drifted would
    be the one deciding whether to start work the other one then refuses."""
    assert not holds(Condition.WITHIN_RUN_CONCURRENCY, _inputs(branches=MAX_CHILDREN_PER_RUN + 1))
    assert not holds(Condition.WITHIN_DEPTH, _inputs(depth=MAX_DELEGATION_DEPTH))


# ------------------------------------------------------ the inputs, read off a real graph
def test_the_gate_inputs_are_read_off_the_graph_and_not_supplied_beside_it():
    """Written from the producer's own output rather than from inputs built to match, which
    is the trap `lark_wiki.restriction_of` fell into: every test built the value the
    producer makes, so the producer's own branch was never exercised.

    Delete this and `gate_inputs` could report the node count as the branch count, or the
    sum as the critical path, and every condition test above would go on passing because
    they never touch a graph."""
    graph = _splittable()

    inputs = gate_inputs(graph, depth=1)

    assert inputs.branches == len(graph.frontier())
    assert inputs.branches == 3
    assert inputs.depth == 1
    assert inputs.cost_multiplier == graph.cost_multiplier
    assert inputs.speedup == graph.speedup
    assert inputs.largest_share == graph.largest_share


def test_a_plan_that_passes_all_six_fans_out():
    """The positive half of the whole gate, driven end to end from a real weighted graph.

    Delete this and every other test here is about refusals, so a gate that collapsed every
    plan would be green."""
    record = decide("r-1", _splittable(), depth=0, at=NOW)

    assert record.failed == ()
    assert record.verdict is Verdict.PARALLEL
    assert record.parallel
    assert record.evaluated == CONDITION_ORDER


def test_a_serial_chain_collapses_to_a_single_loop():
    """A chain of subtasks has a frontier of one, so there is nothing to split however many
    nodes it holds.

    Delete this and the most common shape a planner produces, a sequence, would be gated on
    its node count."""
    chain = DependencyGraph(
        nodes=(
            _node("s-1", retrieval_tokens=3_000, seconds=20.0),
            _node("s-2", retrieval_tokens=3_000, seconds=20.0),
        ),
        edges=(Edge(before="s-1", after="s-2", coupling_tokens=100),),
    )

    record = decide("r-1", chain, depth=0, at=NOW)

    assert record.verdict is Verdict.SINGLE_LOOP
    assert record.failed == (Condition.ENOUGH_BRANCHES, Condition.SPEEDUP_WORTH_IT)


# ------------------------------------------------------------- the default (M18.2.3)
def test_deleting_every_condition_does_not_make_a_plan_fan_out():
    """**The single loop is the default and not a fallthrough.**

    Called with an empty condition list, the arithmetic concludes that nothing failed. The
    record refuses to carry a parallel verdict anyway, because it did not evaluate all six.
    That is the difference between a default and an else branch: emptying the list reads in
    a diff as a simplification and would otherwise fan out every plan in the system.

    Delete this and the collapse depends entirely on the condition list being non-empty,
    which nothing else checks."""
    with pytest.raises(FanOutError, match="rather than all 6 conditions"):
        decide("r-1", _splittable(), depth=0, at=NOW, order=())

    with pytest.raises(FanOutError, match="rather than all 6 conditions"):
        decide("r-1", _splittable(), depth=0, at=NOW, order=CONDITION_ORDER[:5])


def test_a_record_claiming_parallel_with_a_failed_condition_is_refused():
    """The other half of the same construction, asserted directly on the type so that a
    caller building a record by hand cannot say it either.

    Delete this and a record could report a verdict its own evidence contradicts, and an
    auditor reading the row would believe it."""
    with pytest.raises(FanOutError, match="failed"):
        GateRecord(
            run_id="r-1",
            at=NOW,
            inputs=_inputs(),
            evaluated=CONDITION_ORDER,
            failed=(Condition.ENOUGH_BRANCHES,),
            verdict=Verdict.PARALLEL,
        )


def test_a_single_loop_record_may_say_anything_about_what_it_evaluated():
    """The asymmetry is deliberate and worth pinning: the constraint is on the permissive
    verdict only, so a partially evaluated gate can still record that it collapsed.

    Delete this and somebody tightening the constructor would make the fail-safe direction
    the one with the paperwork on it, which is what `brain.ops.halt` refuses in the same
    words about resuming."""
    record = GateRecord(
        run_id="r-1",
        at=NOW,
        inputs=_inputs(),
        evaluated=(Condition.ENOUGH_BRANCHES,),
        failed=(Condition.ENOUGH_BRANCHES,),
        verdict=Verdict.SINGLE_LOOP,
    )

    assert not record.parallel


# ------------------------------------------------------------------ the record (M18.2.4)
def test_a_record_reporting_a_failure_it_never_evaluated_is_refused():
    """A row saying a condition it did not ask came out no is a row an auditor cannot use.

    Delete this and a record could carry any failure at all, and the evidence would stop
    being evidence."""
    with pytest.raises(FanOutError, match="does not list them as evaluated"):
        GateRecord(
            run_id="r-1",
            at=NOW,
            inputs=_inputs(),
            evaluated=(Condition.ENOUGH_BRANCHES,),
            failed=(Condition.SPEEDUP_WORTH_IT,),
            verdict=Verdict.SINGLE_LOOP,
        )


def test_a_record_with_no_run_or_a_naive_timestamp_is_refused():
    """Two conditions with one message each and no positive case worth stating separately: a
    record nobody can find again answers nothing, and two records from two hosts with naive
    timestamps cannot be put in order.

    Delete this and an audit row could be undated and unattributed, which is a row that
    exists and cannot be read."""
    with pytest.raises(FanOutError, match="naming no run"):
        GateRecord(
            run_id=" ",
            at=NOW,
            inputs=_inputs(),
            evaluated=CONDITION_ORDER,
            failed=(),
            verdict=Verdict.PARALLEL,
        )
    with pytest.raises(FanOutError, match="no timezone"):
        GateRecord(
            run_id="r-1",
            at=datetime(2026, 9, 8, 4, 0),
            inputs=_inputs(),
            evaluated=CONDITION_ORDER,
            failed=(),
            verdict=Verdict.PARALLEL,
        )


def test_negative_inputs_are_refused():
    """A plan cannot have fewer than no branches at less than no depth, and a negative
    branch count would pass the concurrency ceiling while failing the branch floor, which
    reads as a plan that is too small rather than as a nonsense.

    Delete this and a miscount upstream would be reported as a legitimate verdict."""
    with pytest.raises(FanOutError, match="cannot have"):
        GateInputs(branches=-1, depth=0, cost_multiplier=1.0, speedup=2.0, largest_share=0.4)


def test_gate_record_gaps_reports_a_field_that_would_carry_a_question():
    """A gate record exists so somebody can ask afterwards why a run split, and six numbers
    answer that completely. A field holding the question would be a copy of somebody's data
    on an operational surface with its own retention.

    Both halves, and the healthy surface first, because a diagnostic that can only be run
    against the healthy tree cannot be shown to fail.

    Delete this and somebody making an audit row more useful would add the question to
    it."""

    @dataclass(frozen=True)
    class Helpful:
        run_id: str
        question: str

    assert gate_record_gaps() == ()

    findings = gate_record_gaps((Helpful,))
    assert findings == ("Helpful.question",)


# ------------------------------------------------------------------ dispatch (M18.2.2)
def test_children_may_not_start_after_a_single_loop_verdict():
    """ "Evaluated before any child starts" made into a shape: the gate record is an input to
    dispatch, so starting children without one is not expressible.

    Delete this and the verdict becomes advisory, and an advisory gate is the thing that is
    switched off during an incident."""
    record = decide("r-1", _splittable(), depth=MAX_DELEGATION_DEPTH, at=NOW)

    refusals = dispatch_refusals(record, ("s-1", "s-2"))

    assert record.verdict is Verdict.SINGLE_LOOP
    assert any("runs as one loop" in one for one in refusals)


def test_more_children_than_the_gate_weighed_are_refused():
    """A plan gated on two branches and dispatched as four is a plan two of whose children
    were never weighed, so the arithmetic was done over a different run.

    Delete this and the gate could be passed with a small plan and the run fanned out over
    a larger one."""
    record = decide("r-1", _splittable(), depth=0, at=NOW)

    refusals = dispatch_refusals(record, ("s-1", "s-2", "s-3", "s-4"))

    assert len(refusals) == 1
    assert "smaller plan" in refusals[0]


def test_a_child_dispatched_twice_is_refused():
    """One subtask counted once by the gate and started twice is a side effect performed
    twice, which is the failure `brain.ops.idempotency` exists for at the other end.

    Delete this and a duplicated child would pass every count-based check, because the
    length is still within the frontier."""
    record = decide("r-1", _splittable(), depth=0, at=NOW)

    refusals = dispatch_refusals(record, ("s-1", "s-1"))

    assert len(refusals) == 1
    assert "started twice" in refusals[0]


def test_the_children_the_gate_weighed_are_admitted():
    """The positive half. A dispatch check tested only by its refusals is satisfied by one
    that refuses every fan-out.

    Delete this and the gate could pass and nothing could ever be dispatched."""
    record = decide("r-1", _splittable(), depth=0, at=NOW)

    assert record.parallel
    assert dispatch_refusals(record, ("s-1",)) == ()
    assert dispatch_refusals(record, ("s-1", "s-2", "s-3")) == ()
