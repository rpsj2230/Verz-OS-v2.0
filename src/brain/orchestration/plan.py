"""What the model proposed, and the graph the arithmetic is then done on.

Architecture section 14 states the division in five words: **the model proposes; arithmetic
decides**. This module is both halves of that sentence's first clause, and the boundary
between them is the thing worth reading.

**A proposal names subtasks and dependencies and cannot name a number.** That is the whole
of `PLANNER_SETS_NO_WEIGHTS` and it is the reason `read_proposal` refuses a key rather than
ignoring it. The fan-out gate in `brain.orchestration.fanout` is pure arithmetic over the
node and edge weights of this graph, so a planner that could set a weight could set the
gate's answer: proposing a plan whose branches are cheap and whose coupling is nothing is a
sentence a model can produce, and every condition the gate evaluates would then be
evaluated against numbers the thing being gated wrote. So the weights come from the system.
Node weight is `brain.ops.spend.estimate`, which is the estimator the budget already uses,
and coupling is measured by whoever knows what a split would duplicate. The proposal is
structure and nothing else.

The refusal is a refusal and not a filter, for the reason
`brain.ops.automation.assert_deterministic` refuses an unrecognised step: a proposal with
an ignored field is a proposal whose author believes the field did something, and the next
version of the planner will send more of them.

**An edge with no coupling weight is refused, because the missing value is the flattering
one.** Coupling is the shared context a split would duplicate; absent, it reads as zero,
zero makes the cost multiplier exactly one, and a multiplier of one passes the gate's cost
condition every time. So an unmeasured edge cannot be admitted with a default: the honest
answer to "how much would this split duplicate" is a number somebody produced, and the
alternative is a gate that approves fan-out precisely where nobody has looked. See
`AN_UNWEIGHTED_EDGE_PASSES_EVERY_CONDITION`.

**The graph is acyclic and this module is where that is decided.** A cycle is not a
degraded plan, it is not a plan: no wave has anything ready, so nothing starts, and a run
that collapses to a single loop still has to execute the subtasks in some order. Cycle
detection lives in `DependencyGraph.__post_init__` and `plan_refusals` asks the graph
rather than walking the edges again, because two cycle detectors is two answers to whether
a run can start.

**Node weight is estimated cost and it is estimated by the estimator the budget uses.**
`brain.ops.spend.estimate` rather than a figure per subtask, because the number the gate
divides has to be the number the budget was sized against; a second cost model here would
let a plan pass the gate and be refused by `brain.ops.spend.preflight` a moment later, and
the person would be told the system is busy about a fan-out that never fitted.

Rejected: letting the planner supply its own cost estimate as a hint the system may
override. A hint that is usually accepted is a value in practice, and the override is the
line somebody deletes when the estimator is slow.

Rejected: deriving coupling from the dependency structure, on the reading that two subtasks
that share a dependency share its context. It is nearly true and it is unmeasurable, and an
unmeasurable weight in an arithmetic gate is a gate whose answer nobody can argue with.

Rejected: a `Plan` type holding proposals, contracts and a graph. It would be one value to
pass around and it would let two of the three be built from different proposals; the graph
already refuses an edge naming a subtask it does not hold, and `plan_refusals` is where the
contracts and the graph are checked against each other.

Scope: domain logic. Nothing here calls a model, and the proposal arrives as data for the
reason `brain.gate.leash` takes its simulation and execution as callables: the loop that
would ask a model for a plan does not exist in this repository, and inventing one here
would be a second runtime for the real one to be reconciled with.

Task ids: M18.1.1, M18.2.1
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.ops.spend import CostInputs, estimate
from brain.orchestration.contract import SubtaskContract

# ------------------------------------------------------------------ written-down reasons
#: Why a proposal may carry structure and never a number.
PLANNER_SETS_NO_WEIGHTS: Final = (
    "The fan-out gate is pure arithmetic over this graph's node and edge weights, so "
    "whoever sets the weights sets the verdict. A planner that could state the cost of its "
    "own branches, or the coupling between them, could talk its way past every condition "
    "the gate evaluates by proposing that the branches are cheap and the split duplicates "
    "nothing, which is a sentence a model produces readily and no arithmetic can "
    "contradict. So a proposal is structure: which subtasks there are and what depends on "
    "what. The weights come from the system, node weight from the estimator the budget is "
    "sized against and coupling from whoever measured it."
)

#: Why an edge with no coupling weight cannot be admitted with a default.
AN_UNWEIGHTED_EDGE_PASSES_EVERY_CONDITION: Final = (
    "Coupling is the shared context a split would duplicate. Absent, the obvious default "
    "is zero; zero duplication makes the cost multiplier exactly one; and a multiplier of "
    "one passes the gate's cost condition whatever else is true. So the default admits "
    "fan-out exactly where nobody has measured what it costs, which is the opposite of "
    "what a default should do here. An unmeasured edge is refused instead, and the plan "
    "collapses to a single loop, which is the answer the whole gate defaults to anyway."
)

#: Keys a proposal may not carry, because carrying one would let the proposer set the gate.
#: Names rather than a rule about values, because the failure arrives as a field somebody
#: adds to make a planner more useful, and it arrives with one of these names on it.
WEIGHT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "cost",
        "cost_minor",
        "coupling",
        "coupling_tokens",
        "duration",
        "estimate",
        "minor",
        "priority",
        "seconds",
        "tokens",
        "weight",
    }
)

#: The keys a proposal may carry. Closed, so a planner adding a field on its own release
#: schedule is refused rather than silently ignored.
PROPOSAL_KEYS: Final[frozenset[str]] = frozenset({"subtask_id", "depends_on"})


class PlanError(Exception):
    """A proposal or a graph that cannot be run.

    Outside the `brain.core.errors` taxonomy, like `brain.orchestration.contract.ContractError`
    and for the same reason: nobody asking a question ever sees one.
    """


# ------------------------------------------------------------- the proposal (M18.1.1)
@dataclass(frozen=True)
class Proposal:
    """One subtask the planner proposed, and what it needs first.

    Two fields, and there is nowhere here for a third that carries a number. See
    `PLANNER_SETS_NO_WEIGHTS`: the type is the boundary, and `read_proposal` is the check
    that a payload from outside cannot get round it.
    """

    subtask_id: str
    #: Subtask ids this one needs the results of. Order is not significant.
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            msg = "a proposed subtask with no id cannot be depended on or dispatched"
            raise PlanError(msg)
        if self.subtask_id in self.depends_on:
            msg = (
                f"{self.subtask_id!r} depends on itself, so it is never ready and the run "
                "stops with nothing to report and nothing to blame"
            )
            raise PlanError(msg)


def read_proposal(raw: Sequence[Mapping[str, object]]) -> tuple[Proposal, ...]:
    """Read a planner's proposal, refusing anything that would let it set its own weights.

    Proposals arrive as data from a model, so they are validated as untrusted input rather
    than typed, exactly as `brain.ops.automation.assert_deterministic` validates a flow
    descriptor. A key nobody declared is refused rather than dropped: a planner sending a
    field believes the field did something, and dropping it silently means the next version
    of the planner sends more of them.

    A weight key is named separately in the message from a merely unknown one. They are both
    refused, and the difference matters to whoever is reading the failure: an unknown key is
    a version skew, and a weight key is the planner trying to price its own plan.
    """
    parsed: list[Proposal] = []
    for index, item in enumerate(raw):
        offered = set(item)
        weights = sorted(offered & WEIGHT_KEYS)
        if weights:
            msg = f"proposal {index} carries {weights}. {PLANNER_SETS_NO_WEIGHTS}"
            raise PlanError(msg)
        unknown = sorted(offered - PROPOSAL_KEYS)
        if unknown:
            msg = (
                f"proposal {index} carries {unknown}, which no proposal may hold; declared "
                f"keys are {sorted(PROPOSAL_KEYS)}"
            )
            raise PlanError(msg)
        subtask_id = item.get("subtask_id")
        if not isinstance(subtask_id, str):
            msg = f"proposal {index} names {subtask_id!r} as its subtask id, which is not a string"
            raise PlanError(msg)
        depends = item.get("depends_on", ())
        if isinstance(depends, str) or not isinstance(depends, (list, tuple)):
            # A bare string is the shape that reads as working and is not: iterating it
            # yields one dependency per character, and every one of them names nothing, so
            # the graph refuses with a message about unknown subtasks rather than about the
            # type. `brain.core.scope.Clause` refuses the same shape for the same reason.
            msg = (
                f"proposal {index} gives {depends!r} as its dependencies; a list is "
                "required, and a bare string would be read one character at a time"
            )
            raise PlanError(msg)
        for one in depends:
            if not isinstance(one, str):
                msg = f"proposal {index} depends on {one!r}, which is not a subtask id"
                raise PlanError(msg)
        parsed.append(
            Proposal(subtask_id=subtask_id, depends_on=tuple(str(one) for one in depends))
        )
    return tuple(parsed)


# ------------------------------------------------------------- the graph (M18.2.1)
@dataclass(frozen=True)
class Node:
    """One subtask, weighted by what it is estimated to cost and how long it is expected to take.

    Cost is carried as `brain.ops.spend.CostInputs` rather than as a number, so that the
    figure the gate divides is produced by the estimator the budget was sized against and
    can be re-derived from the trace. `brain.ops.spend.Estimate` carries its inputs for the
    same reason.

    Duration is separate from cost and is not derived from it. They disagree exactly where
    the gate needs them to: a subtask that waits on a slow connector is cheap and long, and
    one that reads a large context is expensive and quick. A single weight would make the
    speedup condition and the cost condition the same condition.
    """

    subtask_id: str
    cost: CostInputs
    #: Expected wall-clock seconds. Strictly positive: a subtask of no duration makes the
    #: critical path zero and the speedup infinite, which passes the gate for free.
    seconds: float

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            msg = "a graph node with no subtask id cannot be matched to a contract or a result"
            raise PlanError(msg)
        if self.seconds <= 0:
            msg = (
                f"node {self.subtask_id!r} is expected to take {self.seconds} seconds; a "
                "subtask of no duration makes the critical path zero and the speedup "
                "unbounded, which passes the gate whatever the plan actually is"
            )
            raise PlanError(msg)

    @property
    def tokens(self) -> int:
        """The estimated size of this subtask, from the estimator the budget uses."""
        return estimate(self.cost).tokens


@dataclass(frozen=True)
class Edge:
    """One dependency, weighted by the context a split would duplicate.

    `before` has to finish for `after` to start. `coupling_tokens` is what the two share and
    what each end would have to re-establish for itself once they are no longer one loop.
    """

    before: str
    after: str
    coupling_tokens: int

    def __post_init__(self) -> None:
        if self.before == self.after:
            msg = f"{self.before!r} depends on itself, so it is never ready"
            raise PlanError(msg)
        if self.coupling_tokens < 0:
            msg = (
                f"the edge {self.before!r} to {self.after!r} carries {self.coupling_tokens} "
                "coupling tokens; a negative duplication is a split that saves context, "
                "which would make the cost multiplier less than one"
            )
            raise PlanError(msg)


@dataclass(frozen=True)
class DependencyGraph:
    """The plan as weighted structure: what has to happen first, and what each part costs.

    Refuses at construction rather than at read time, so a graph that exists is a graph the
    arithmetic can be done on. The alternative is a `waves()` that raises, which puts the
    failure at whichever caller happened to ask first and leaves every other caller free to
    read the totals off a graph that cannot run.
    """

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...] = ()

    def __post_init__(self) -> None:
        ids = [one.subtask_id for one in self.nodes]
        duplicated = sorted({one for one in ids if ids.count(one) > 1})
        if duplicated:
            msg = f"{duplicated} name more than one node, so an edge naming one names two"
            raise PlanError(msg)
        if not self.nodes:
            msg = "a dependency graph with no nodes describes no work and cannot be gated"
            raise PlanError(msg)
        known = set(ids)
        for edge in self.edges:
            missing = sorted({edge.before, edge.after} - known)
            if missing:
                msg = (
                    f"the edge {edge.before!r} to {edge.after!r} names {missing}, which this "
                    "graph does not hold, so the wave order would be computed over a "
                    "structure nothing is going to run"
                )
                raise PlanError(msg)
        seen = {(edge.before, edge.after) for edge in self.edges}
        if len(seen) != len(self.edges):
            msg = (
                "the same dependency appears twice, so its coupling is counted twice in the "
                "duplication total and once in the wave order"
            )
            raise PlanError(msg)
        if self._ordered() is None:
            msg = (
                "this graph has a cycle, so no subtask is ever ready and the run starts "
                "nothing; a cycle is not a plan that parallelises badly, it is not a plan"
            )
            raise PlanError(msg)

    # -------------------------------------------------------------------- structure
    def _ordered(self) -> tuple[tuple[str, ...], ...] | None:
        """The waves, or None when the graph has a cycle. Kahn's algorithm.

        Private and returning None, with the public `waves` raising nothing at all, because
        the constructor has already refused a cyclic graph: this is the one call that has to
        cope with one, and it is the call the constructor makes.
        """
        remaining = {one.subtask_id: 0 for one in self.nodes}
        after: dict[str, list[str]] = {one.subtask_id: [] for one in self.nodes}
        for edge in self.edges:
            remaining[edge.after] += 1
            after[edge.before].append(edge.after)
        waves: list[tuple[str, ...]] = []
        ready = sorted(one for one, count in remaining.items() if count == 0)
        placed = 0
        while ready:
            waves.append(tuple(ready))
            placed += len(ready)
            following: list[str] = []
            for one in ready:
                for nxt in after[one]:
                    remaining[nxt] -= 1
                    if remaining[nxt] == 0:
                        following.append(nxt)
            ready = sorted(following)
        if placed != len(self.nodes):
            return None
        return tuple(waves)

    def waves(self) -> tuple[tuple[str, ...], ...]:
        """The subtasks in the order they become ready, each wave sorted by id.

        Sorted rather than in insertion order, so two readings of one plan produce the same
        list and a trace of a run can be compared with a trace of the same run replayed.
        """
        ordered = self._ordered()
        if ordered is None:  # pragma: no cover - the constructor refuses a cyclic graph
            msg = "this graph has a cycle, which the constructor should have refused"
            raise PlanError(msg)
        return ordered

    def frontier(self) -> tuple[str, ...]:
        """The subtasks that could start at once, which is what there is to parallelise.

        The first wave and not the node count. A chain of five subtasks has five nodes and a
        frontier of one, and fanning out over it buys nothing at all while looking, to any
        condition counting nodes, exactly like five independent branches.
        """
        return self.waves()[0]

    def node_for(self, subtask_id: str) -> Node:
        for one in self.nodes:
            if one.subtask_id == subtask_id:
                return one
        msg = f"this graph holds no node {subtask_id!r}"
        raise PlanError(msg)

    # ---------------------------------------------------------------------- weights
    @property
    def serial_tokens(self) -> int:
        """What one loop would spend: every subtask once, the shared context read once."""
        return sum(one.tokens for one in self.nodes)

    @property
    def duplicated_tokens(self) -> int:
        """What splitting would spend again: the shared context, once per edge that spans a split.

        Every edge, because every dependency in a fanned-out plan has its two ends in
        different children and each of them has to establish the context for itself. In a
        single loop that context is read once and carried, which is exactly why a single
        loop is cheaper and slower.
        """
        return sum(edge.coupling_tokens for edge in self.edges)

    @property
    def parallel_tokens(self) -> int:
        return self.serial_tokens + self.duplicated_tokens

    @property
    def cost_multiplier(self) -> float:
        """What fanning out multiplies the spend by. One means it duplicates nothing.

        `serial_tokens` cannot be zero: every node has a positive duration and a cost the
        estimator produced, and a plan of nothing is refused by the constructor. The guard
        is written anyway, because a zero here would be a division that reports a plan as
        infinitely expensive and a plan as free depending on which way the estimator was
        wrong.
        """
        serial = self.serial_tokens
        if serial <= 0:
            msg = (
                "this graph's subtasks are estimated at no tokens at all, so the cost "
                "multiplier is undefined and every cost condition would be decided by a "
                "division by zero"
            )
            raise PlanError(msg)
        return self.parallel_tokens / serial

    @property
    def serial_seconds(self) -> float:
        return sum(one.seconds for one in self.nodes)

    @property
    def critical_path_seconds(self) -> float:
        """The longest path through the graph, which is what a fanned-out run would take.

        The whole point of parallelism is that the latency is the slowest chain rather than
        the sum, so this is the number the speedup is measured against. Computed over the
        wave order, which the constructor has already proved exists.
        """
        longest: dict[str, float] = {}
        arrives: dict[str, list[str]] = {one.subtask_id: [] for one in self.nodes}
        for edge in self.edges:
            arrives[edge.after].append(edge.before)
        for wave in self.waves():
            for one in wave:
                before = max((longest[earlier] for earlier in arrives[one]), default=0.0)
                longest[one] = before + self.node_for(one).seconds
        return max(longest.values(), default=0.0)

    @property
    def speedup(self) -> float:
        """How much faster the fanned-out run would be. One means it would not be.

        The critical path is at least the duration of one node and every node is strictly
        positive, so this cannot divide by zero for any graph the constructor admitted.
        """
        return self.serial_seconds / self.critical_path_seconds

    @property
    def largest_share(self) -> float:
        """The biggest subtask as a fraction of the whole plan's estimated cost.

        Amdahl's law as a single number. A plan whose work is one large subtask and several
        small ones has nothing worth splitting however many branches it reports, and this is
        the reading that survives a duration estimate being optimistic, which the speedup is
        not.
        """
        return max(one.tokens for one in self.nodes) / self.serial_tokens


def graph_for(
    proposals: Sequence[Proposal],
    nodes: Sequence[Node],
    coupling: Mapping[tuple[str, str], int],
) -> DependencyGraph:
    """The weighted graph for a proposal, with the weights supplied by the system.

    Three arguments and the separation between them is the design. The proposal is
    structure, from the planner. The nodes are cost and duration, from the estimator. The
    coupling is measured. Nothing here can produce a weight, so nothing here can decide the
    gate's answer; see `PLANNER_SETS_NO_WEIGHTS`.

    Refuses an edge with no coupling weight rather than defaulting it to zero. See
    `AN_UNWEIGHTED_EDGE_PASSES_EVERY_CONDITION`.
    """
    edges: list[Edge] = []
    for proposal in proposals:
        for before in proposal.depends_on:
            key = (before, proposal.subtask_id)
            if key not in coupling:
                msg = (
                    f"the dependency {before!r} to {proposal.subtask_id!r} has no measured "
                    f"coupling. {AN_UNWEIGHTED_EDGE_PASSES_EVERY_CONDITION}"
                )
                raise PlanError(msg)
            edges.append(
                Edge(
                    before=before,
                    after=proposal.subtask_id,
                    coupling_tokens=coupling[key],
                )
            )
    return DependencyGraph(nodes=tuple(nodes), edges=tuple(edges))


def plan_refusals(
    proposals: Sequence[Proposal],
    contracts: Sequence[SubtaskContract],
    graph: DependencyGraph,
) -> tuple[str, ...]:
    """Every way this plan's three parts describe different work.

    Returns all of them rather than the first, matching `brain.ops.queue.queue_url_refusals`.

    Three sets have to agree: what the planner proposed, what each subtask promises to
    return, and what the graph will be weighed as. Any of them missing an entry the others
    hold is a plan that runs something nobody specified, specifies something nothing runs,
    or weighs something that is not there. None of the three is authoritative over the other
    two, which is why this compares them rather than deriving two from one: deriving would
    make a mismatch impossible to see and would move the failure to whichever of the three
    was built first.

    Acyclicity is deliberately not re-checked here. `DependencyGraph` refuses a cyclic graph
    at construction, and a second cycle detector would be a second answer to whether a run
    can start.
    """
    findings: list[str] = []
    proposed = {one.subtask_id for one in proposals}
    promised = {one.subtask_id for one in contracts}
    weighed = {one.subtask_id for one in graph.nodes}
    findings.extend(
        f"{one!r} was proposed and has no contract, so nothing says what it returns and "
        "its result cannot be validated before it is merged"
        for one in sorted(proposed - promised)
    )
    findings.extend(
        f"{one!r} has a contract and was not proposed, so nothing dispatches it and the "
        "merge waits for a result that is never coming"
        for one in sorted(promised - proposed)
    )
    findings.extend(
        f"{one!r} was proposed and is not in the weighted graph, so the gate decides "
        "whether to fan out over a plan smaller than the one that would run"
        for one in sorted(proposed - weighed)
    )
    findings.extend(
        f"{one!r} is weighed and was not proposed, so the gate is deciding about work "
        "nothing is going to do"
        for one in sorted(weighed - proposed)
    )
    for proposal in proposals:
        findings.extend(
            f"{proposal.subtask_id!r} depends on {one!r}, which nothing proposes"
            for one in sorted(set(proposal.depends_on) - proposed)
        )
    return tuple(findings)
