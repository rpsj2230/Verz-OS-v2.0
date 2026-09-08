"""The model proposes structure; the system supplies every number the gate divides.

The property most of this file is about is that a planner cannot price its own plan. The
fan-out gate is pure arithmetic over the weights of this graph, so a proposal carrying one
would let the thing being gated set the gate's answer, and the refusal is asserted against
the whole set of weight keys rather than against one of them.

The node weight is compared against `brain.ops.spend.estimate` rather than against a figure
written here, because a second cost model would let a plan pass the gate and be refused by
the budget a moment later.

Task ids: M18.1.1, M18.2.1
"""

from __future__ import annotations

import pytest

from brain.core.entitlement import Capability
from brain.core.lane import Lane
from brain.models.routing import Tier
from brain.ops.spend import CostInputs, estimate
from brain.orchestration.contract import FieldKind, FieldSpec, SubtaskContract
from brain.orchestration.plan import (
    PROPOSAL_KEYS,
    WEIGHT_KEYS,
    DependencyGraph,
    Edge,
    Node,
    PlanError,
    Proposal,
    graph_for,
    plan_refusals,
    read_proposal,
)

NAME = Capability(value="read:client.name")


def _cost(tool_calls: int = 2, retrieval_tokens: int = 1_000) -> CostInputs:
    return CostInputs(
        lane=Lane.TASK,
        tier=Tier.MAIN,
        tool_calls=tool_calls,
        retrieval_tokens=retrieval_tokens,
    )


def _node(subtask_id: str, *, retrieval_tokens: int = 1_000, seconds: float = 10.0) -> Node:
    return Node(
        subtask_id=subtask_id,
        cost=_cost(retrieval_tokens=retrieval_tokens),
        seconds=seconds,
    )


def _contract(subtask_id: str) -> SubtaskContract:
    return SubtaskContract(
        subtask_id=subtask_id,
        objective="Report the open invoice position for this client",
        output=(FieldSpec(name="balance", kind=FieldKind.DECIMAL),),
        capabilities=(NAME,),
    )


# ------------------------------------------------------------- the proposal (M18.1.1)
def test_a_well_formed_proposal_is_read():
    """The positive half. A boundary tested only by its refusals is satisfied by one that
    refuses everything, and this one stands between a planner and every plan.

    Delete this and `read_proposal` could raise unconditionally, and every refusal test
    below would go on passing."""
    parsed = read_proposal(
        [
            {"subtask_id": "s-1"},
            {"subtask_id": "s-2", "depends_on": ["s-1"]},
        ]
    )

    assert parsed == (
        Proposal(subtask_id="s-1"),
        Proposal(subtask_id="s-2", depends_on=("s-1",)),
    )


@pytest.mark.parametrize("key", sorted(WEIGHT_KEYS))
def test_a_proposal_carrying_any_weight_key_is_refused(key):
    """**The planner cannot price its own plan**, asserted over every key rather than one.

    Parametrised because the failure arrives as whichever field somebody adds to make a
    planner more useful, and a test naming one key covers the one nobody was going to add.

    Delete this and a proposal could state that its branches are cheap and its splits
    duplicate nothing, which passes every arithmetic condition the gate evaluates."""
    with pytest.raises(PlanError, match="pure arithmetic"):
        read_proposal([{"subtask_id": "s-1", key: 1}])


def test_a_proposal_carrying_an_unknown_key_is_refused_rather_than_filtered():
    """A planner sending a field believes the field did something, so dropping it silently
    means the next version of the planner sends more of them.

    Delete this and a proposal could carry anything at all as long as it avoided the weight
    names, which makes the closed key set decorative."""
    with pytest.raises(PlanError, match="which no proposal may hold"):
        read_proposal([{"subtask_id": "s-1", "confidence": 0.9}])
    assert sorted(PROPOSAL_KEYS) == ["depends_on", "subtask_id"]


def test_dependencies_given_as_a_bare_string_are_refused():
    """A bare string iterates one character at a time, so every dependency it produces names
    nothing and the graph refuses with a message about unknown subtasks rather than about
    the type. `brain.core.scope.Clause` refuses the same shape for the same reason.

    Delete this and a planner sending `"s-1"` instead of `["s-1"]` would produce a confusing
    failure three functions away from the cause."""
    with pytest.raises(PlanError, match="one character at a time"):
        read_proposal([{"subtask_id": "s-2", "depends_on": "s-1"}])


def test_a_proposal_whose_id_is_not_a_string_is_refused():
    """A payload from a model is untrusted input, so a number where an id belongs is refused
    rather than coerced.

    Delete this and `str(1)` would become a subtask id, which matches nothing in the
    contracts and produces a plan-level mismatch instead of a parse failure."""
    with pytest.raises(PlanError, match="not a string"):
        read_proposal([{"subtask_id": 1}])
    with pytest.raises(PlanError, match="not a subtask id"):
        read_proposal([{"subtask_id": "s-1", "depends_on": [2]}])


def test_a_subtask_depending_on_itself_is_refused():
    """It is never ready, so the run stops with nothing to report and nothing to blame.

    Delete this and a self-dependency would reach the graph, where it becomes a cycle and
    produces a message about cycles rather than about the one subtask at fault."""
    with pytest.raises(PlanError, match="depends on itself"):
        Proposal(subtask_id="s-1", depends_on=("s-1",))


# ------------------------------------------------------------- the graph (M18.2.1)
def test_node_weight_is_the_estimator_the_budget_is_sized_against():
    """Compared against `brain.ops.spend.estimate` rather than against a figure written
    here, because the number the gate divides has to be the number the budget was sized
    against.

    Delete this and a second cost model could appear in this module, and a plan would pass
    the gate and be refused by the budget a moment later with the person told the system is
    busy."""
    node = _node("s-1", retrieval_tokens=2_500)

    assert node.tokens == estimate(node.cost).tokens
    assert node.tokens > 0


def test_a_node_of_no_duration_is_refused():
    """A subtask of zero seconds makes the critical path zero and the speedup unbounded,
    which passes the gate's speedup condition for free.

    Delete this and a plan could be admitted by claiming its work takes no time."""
    with pytest.raises(PlanError, match="critical path zero"):
        Node(subtask_id="s-1", cost=_cost(), seconds=0.0)


def test_waves_are_the_order_things_become_ready_and_the_frontier_is_the_first_of_them():
    """A chain of five subtasks has five nodes and a frontier of one, and fanning out over
    it buys nothing while looking, to any condition counting nodes, like five independent
    branches.

    Delete this and the gate's branch count could quietly become the node count, which
    admits every long serial plan as a wide parallel one."""
    chain = DependencyGraph(
        nodes=tuple(_node(f"s-{i}") for i in range(1, 4)),
        edges=(
            Edge(before="s-1", after="s-2", coupling_tokens=10),
            Edge(before="s-2", after="s-3", coupling_tokens=10),
        ),
    )
    wide = DependencyGraph(nodes=tuple(_node(f"s-{i}") for i in range(1, 4)))

    assert chain.waves() == (("s-1",), ("s-2",), ("s-3",))
    assert chain.frontier() == ("s-1",)
    assert wide.waves() == (("s-1", "s-2", "s-3"),)
    assert wide.frontier() == ("s-1", "s-2", "s-3")


def test_a_cycle_is_refused_at_construction_rather_than_at_read_time():
    """A `waves()` that raised would put the failure at whichever caller asked first and
    leave every other caller free to read the totals off a graph that cannot run.

    Delete this and a cyclic plan could be weighed, gated and dispatched, and no subtask in
    it would ever be ready."""
    with pytest.raises(PlanError, match="has a cycle"):
        DependencyGraph(
            nodes=(_node("s-1"), _node("s-2")),
            edges=(
                Edge(before="s-1", after="s-2", coupling_tokens=10),
                Edge(before="s-2", after="s-1", coupling_tokens=10),
            ),
        )


def test_an_edge_naming_a_node_the_graph_does_not_hold_is_refused():
    """The wave order would be computed over a structure nothing is going to run.

    Delete this and an edge could point at a subtask that was dropped from the plan, and the
    dependant would never become ready."""
    with pytest.raises(PlanError, match="which this graph does not hold"):
        DependencyGraph(
            nodes=(_node("s-1"),),
            edges=(Edge(before="s-1", after="s-9", coupling_tokens=10),),
        )


def test_the_same_dependency_twice_is_refused():
    """Its coupling would be counted twice in the duplication total and once in the wave
    order, so the cost multiplier and the structure would disagree about the same plan.

    Delete this and a duplicated edge would inflate the multiplier, which fails closed, and
    the failure would be silent."""
    with pytest.raises(PlanError, match="the same dependency appears twice"):
        DependencyGraph(
            nodes=(_node("s-1"), _node("s-2")),
            edges=(
                Edge(before="s-1", after="s-2", coupling_tokens=10),
                Edge(before="s-1", after="s-2", coupling_tokens=20),
            ),
        )


def test_negative_coupling_and_duplicate_nodes_and_an_empty_graph_are_refused():
    """Three constructor refusals in one test because each is a single condition with a
    single message and none of them has a positive case worth stating separately.

    Delete this and a split that claims to save context would make the cost multiplier less
    than one, which passes the gate however expensive the plan is."""
    with pytest.raises(PlanError, match="negative duplication"):
        Edge(before="s-1", after="s-2", coupling_tokens=-1)
    with pytest.raises(PlanError, match="name more than one node"):
        DependencyGraph(nodes=(_node("s-1"), _node("s-1")))
    with pytest.raises(PlanError, match="describes no work"):
        DependencyGraph(nodes=())


def test_the_cost_multiplier_counts_every_edges_coupling_once():
    """In a single loop the shared context is read once and carried; in a fan-out each end
    of every dependency establishes it for itself.

    Delete this and the duplication could be counted per node or not at all, and the
    multiplier would stop measuring what a split costs."""
    graph = DependencyGraph(
        nodes=(_node("s-1"), _node("s-2"), _node("s-3")),
        edges=(
            Edge(before="s-1", after="s-3", coupling_tokens=400),
            Edge(before="s-2", after="s-3", coupling_tokens=600),
        ),
    )

    assert graph.duplicated_tokens == 1_000
    assert graph.parallel_tokens == graph.serial_tokens + 1_000
    assert graph.cost_multiplier == graph.parallel_tokens / graph.serial_tokens


def test_the_critical_path_is_the_longest_chain_and_not_the_sum():
    """The whole point of parallelism is that the latency is the slowest chain, so the
    speedup is measured against this rather than against the total.

    Delete this and the critical path could become the sum, which makes every speedup
    exactly one, or the maximum node, which ignores the structure entirely."""
    graph = DependencyGraph(
        nodes=(
            _node("s-1", seconds=5.0),
            _node("s-2", seconds=7.0),
            _node("s-3", seconds=3.0),
        ),
        edges=(Edge(before="s-1", after="s-3", coupling_tokens=10),),
    )

    assert graph.serial_seconds == 15.0
    assert graph.critical_path_seconds == 8.0
    assert graph.speedup == 15.0 / 8.0


def test_the_largest_share_is_one_subtask_against_the_whole_plan():
    """Amdahl's law as a single number, and the reading that survives an optimistic duration
    estimate.

    Delete this and the dominance condition would have nothing to evaluate, and a plan that
    is one large subtask with decoration would fan out whenever its durations flattered
    it."""
    graph = DependencyGraph(
        nodes=(
            _node("s-1", retrieval_tokens=90_000),
            _node("s-2", retrieval_tokens=1_000),
        )
    )

    assert graph.largest_share > 0.9
    assert graph.largest_share <= 1.0


# ------------------------------------------------------------------ weighing a proposal
def test_an_edge_with_no_measured_coupling_is_refused_rather_than_defaulted_to_zero():
    """**The missing value is the flattering one.** Zero duplication makes the multiplier
    exactly one, and a multiplier of one passes the cost condition whatever else is true, so
    a default would admit fan-out precisely where nobody has measured it.

    Delete this and an unmeasured plan becomes the easiest plan to get through the gate."""
    proposals = (Proposal(subtask_id="s-1"), Proposal(subtask_id="s-2", depends_on=("s-1",)))
    nodes = (_node("s-1"), _node("s-2"))

    with pytest.raises(PlanError, match="no measured coupling"):
        graph_for(proposals, nodes, {})

    graph = graph_for(proposals, nodes, {("s-1", "s-2"): 250})
    assert graph.duplicated_tokens == 250


# ------------------------------------------------------------------------- the diagnostic
def test_plan_refusals_reports_every_way_the_three_parts_describe_different_work():
    """Proposals, contracts and the weighted graph all have to agree, and none of the three
    is authoritative over the other two.

    Delete this and a plan could run a subtask nobody specified, specify one nothing runs,
    or gate a run smaller than the one about to happen, and each of the three would look
    correct read on its own."""
    proposals = (Proposal(subtask_id="s-1"), Proposal(subtask_id="s-2", depends_on=("s-9",)))
    contracts = (_contract("s-1"), _contract("s-3"))
    graph = DependencyGraph(nodes=(_node("s-1"), _node("s-4")))

    findings = plan_refusals(proposals, contracts, graph)

    assert any("'s-2' was proposed and has no contract" in one for one in findings)
    assert any("'s-3' has a contract and was not proposed" in one for one in findings)
    assert any("'s-2' was proposed and is not in the weighted graph" in one for one in findings)
    assert any("'s-4' is weighed and was not proposed" in one for one in findings)
    assert any("depends on 's-9'" in one for one in findings)


def test_a_plan_whose_three_parts_agree_is_reported_clean():
    """The positive half, and the reason the diagnostic takes its inputs: a check that can
    only be run against a broken plan cannot be shown to pass, and one that can only be run
    against a healthy one cannot be shown to fail.

    Delete this and `plan_refusals` could report something for every plan, which would stop
    any run from starting."""
    proposals = (Proposal(subtask_id="s-1"), Proposal(subtask_id="s-2", depends_on=("s-1",)))
    contracts = (_contract("s-1"), _contract("s-2"))
    graph = graph_for(proposals, (_node("s-1"), _node("s-2")), {("s-1", "s-2"): 100})

    assert plan_refusals(proposals, contracts, graph) == ()


@pytest.mark.parametrize("blank", ["", " "])
def test_a_proposal_or_a_node_naming_no_subtask_is_refused(blank):
    """A proposed subtask with no id cannot be depended on or dispatched, and a graph node
    with none cannot be matched to a contract or to a result.

    Whitespace as well as the empty string, because a strip-free check admits a space and
    every set comparison in `plan_refusals` would then match it against another blank.

    Delete this and a plan could carry an anonymous subtask that weighs something, gates
    something and merges nothing."""
    with pytest.raises(PlanError, match="cannot be depended on"):
        Proposal(subtask_id=blank)
    with pytest.raises(PlanError, match="cannot be matched to a contract"):
        Node(subtask_id=blank, cost=_cost(), seconds=1.0)


def test_an_edge_from_a_subtask_to_itself_is_refused():
    """It is never ready, and the constructor is where it is caught rather than the cycle
    check, so the message names the one subtask at fault rather than the graph.

    `Proposal` refuses the same shape, and both are needed: a graph can be built from edges
    without going through a proposal at all, which is how `graph_for`'s callers and the
    fan-out tests build one.

    Delete this and a self-edge would be reported as a cycle, which sends the reader looking
    for two subtasks."""
    with pytest.raises(PlanError, match="depends on itself"):
        Edge(before="s-1", after="s-1", coupling_tokens=10)


def test_a_plan_estimated_at_no_tokens_at_all_refuses_to_report_a_multiplier():
    """Reachable rather than defensive: a fast-lane node costs nothing by definition, because
    `brain.core.lane.Lane.FAST` runs no model and `brain.models.routing.Tier.NONE` is priced
    at zero. A graph of them has a serial cost of zero, and the cost multiplier would be a
    division by it.

    Refused rather than defaulted, because the two plausible defaults are opposite: zero
    reports every plan as free and passes the cost condition, and infinity reports every plan
    as ruinous and fails it.

    Delete this and a plan of fast-lane subtasks would either always fan out or never, and
    which one would depend on how the division happened to behave."""
    free = DependencyGraph(
        nodes=(
            Node(
                subtask_id="s-1",
                cost=CostInputs(lane=Lane.FAST, tier=Tier.NONE),
                seconds=1.0,
            ),
        )
    )

    assert free.serial_tokens == 0
    with pytest.raises(PlanError, match="undefined"):
        _ = free.cost_multiplier
