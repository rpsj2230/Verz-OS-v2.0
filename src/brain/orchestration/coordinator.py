"""A coordinating agent hands subtasks to specialists, and no child reaches more than the asker.

`brain.orchestration` was a package of refusals nothing called: a contract for what a subtask
returns, the chain a child's reach is folded along, the caps on depth and concurrency, the global
parallelism budget, the gate that weighs a plan, and a merge that states a gap. This is the module
that asks them, in the order a run needs them, of a plan whose steps name the specialist agent that
does each. It is the **deterministic half of a coordinating agent**: it never calls a model to split
a request (`brain.orchestration.planner` does, and its reply is checked before it gets here) and it
never calls a specialist except through the port it is handed.

**A specialist is refused before it starts, and the refusal is one sentence for two causes.** A
coordinator may hand a subtask only to an agent an administrator allowed it to call
(`callee_refusals`). An agent that was never allowed and an agent that does not exist or cannot be
loaded get the same sentence, because a planner is a model and a model that can tell the two apart
by the words it is refused with can enumerate the company's agents by trying slugs. See
`A_CALLEE_THAT_IS_NOT_ALLOWED_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_REFUSAL`.

**Every child is run at the asker's reach narrowed by every lens on the way, folded by the one
intersection.** The chain is the coordinator's agent hop, the specialist's agent hop and the
subtask's own ceiling, in that order, through `brain.orchestration.delegation.chain_reach`, which
calls `brain.ops.automation.flow_reach`, which calls `EntitlementSet.intersect`. **Nothing here
intersects anything**, and `tests/invariants/test_single_implementation.py` pins that this module is
in none of its call sites. What the model proposes cannot widen it: the planner sets no ceiling,
and the capabilities a subtask is allowed are read from the specialist's own ceiling by
`contract_for`, so the subtask lens is the specialist's lens again and the model has no word for a
narrower or a wider one. See `A_PLANNER_CHOOSES_WHO_AND_NEVER_WHAT_THEY_MAY_REACH`.

**The depth cap and the per-run cap are asked at dispatch, of what actually starts together.**
`brain.orchestration.delegation.chain_refusals` is asked of every child's chain and
`concurrency_refusals` of each wave that starts at once (M18.3.4). The gate's conditions mirror
both and are not the same check: the gate counts the first wave, a later wave can be wider, and a
wave wider than the cap is run one child at a time and the reason is recorded
(`Why.WAVE_OVER_THE_CAP`) rather than started and refused half way.

**The global budget is asked once, for the widest wave, before any child starts** (M18.3.5). One
request for all of a wave's children, never one per child, for the reason
`brain.orchestration.delegation.fan_out_request` records: a fan-out admitted child by child half
happens, and the merge cannot tell a child that failed from one that was never admitted. A budget
with no room does not refuse the run. It runs the specialists one after another and says so
(`Why.NO_ROOM`). A halt does refuse it, in the halt's own words, because a stopped estate starts
nothing.

**Not fanning out is not the coordinator doing the work.** When fan-out was not enabled for the
agent, when the gate declines, when a wave is over the cap or when there is no room, the specialists
run **one after another** and every one of them still runs at its own reach
(`SPECIALISTS_RUN_ONE_AFTER_ANOTHER_AND_NEVER_ARE_REPLACED_BY_THE_COORDINATOR`, M18.7.1). The
cheaper design reads the gate's `single_loop` as "the coordinator answers alone", which is a
coordinator answering at its own ceiling a question it was set up not to answer, and which makes
a refusal of parallelism a way round every specialist's ceiling. There is no code path here on
which the coordinator produces a subtask's result, and the engine takes the result of a step from
the port and from nowhere else. The reason a run was not parallel is **kept with the run**, which
M18.6.2 asks.

**The coordinator receives only a checked result.** A specialist returns values; each is validated
against the contract it answered (`brain.orchestration.contract.result_refusals`) and a result that
does not satisfy it is a stated gap and never a merge input (M18.1.2, M18.1.3). A later step is
handed the earlier steps' validated values and nothing else of them. The specialist's prose, its
tool calls and what it read stay in its own run. The contract has no prose field to put a paragraph
in (M18.1.4), and `contract_for` refuses a kind it does not have.

**A step whose dependency produced nothing is not run.** It is stated as a gap, with a cause an
auditor reads, and the run goes on with what it has, so one failed branch costs the answer a part
and never the whole.

Rejected: running the plan inside `brain.orchestration.fanout`. The gate is arithmetic over a
graph, with no I/O by design, and a module that also dispatched would be a module whose arithmetic
could no longer be tested without a specialist.

Task ids: M18.1.2, M18.1.4, M18.3.4, M18.3.5, M18.5.1, M18.5.2, M18.6.2, M18.7.1
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import structlog

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.models.routing import Tier
from brain.ops.admission import AdmissionRequest
from brain.ops.spend import CostInputs, SpendError
from brain.orchestration.contract import (
    ContractError,
    FieldSpec,
    SubtaskContract,
    ValidatedResult,
    result_refusals,
    subtask_ceiling,
    validated,
)
from brain.orchestration.delegation import (
    Delegation,
    DelegationError,
    Hop,
    LensKind,
    chain_reach,
    chain_refusals,
    child_hops,
    concurrency_refusals,
    depth_of,
    fan_out_request,
)
from brain.orchestration.fanout import FanOutError, GateRecord, decide
from brain.orchestration.merge import (
    Gap,
    GapCause,
    GapTrace,
    MergedAnswer,
    MergeError,
    SubtaskReport,
    merge,
)
from brain.orchestration.plan import (
    DependencyGraph,
    Node,
    PlanError,
    Proposal,
    graph_for,
    plan_refusals,
)

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a callee nobody allowed and a callee nobody has are told the same way.
A_CALLEE_THAT_IS_NOT_ALLOWED_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_REFUSAL: Final = (
    "A plan is proposed by a model, and a model that is refused with different words for an agent "
    "it may not call and an agent that does not exist can enumerate the company's agents by "
    "trying slugs. So both get one sentence, and it names the subtask, which the asker's own "
    "request produced, and never the agent."
)

#: Why the planner has no word for what a specialist may reach.
A_PLANNER_CHOOSES_WHO_AND_NEVER_WHAT_THEY_MAY_REACH: Final = (
    "A plan names, for each subtask, which allowed specialist does it and what it must return. "
    "The capabilities a subtask is allowed are read from the specialist's own ceiling, so the "
    "subtask's lens is the specialist's lens again: a model proposing a plan can neither narrow "
    "nor widen what a child reaches, and a subtask ceiling that confers anything is not a thing "
    "it can say."
)

#: M18.7.1, as the engine keeps it.
SPECIALISTS_RUN_ONE_AFTER_ANOTHER_AND_NEVER_ARE_REPLACED_BY_THE_COORDINATOR: Final = (
    "When a run is not run in parallel its specialists run one after another, each at its own "
    "reach. The coordinator never produces a subtask's result in their place: a refusal of "
    "parallelism that let the coordinator answer would be a way round every specialist's ceiling, "
    "since the coordinator holds a ceiling of its own and not theirs."
)

#: M18.3.5, as the engine keeps it.
ROOM_IS_ASKED_ONCE_FOR_THE_WIDEST_WAVE_BEFORE_ANY_CHILD_STARTS: Final = (
    "The global parallelism budget is asked for the widest wave in one request before any child of "
    "it starts. A fan-out admitted child by child half happens, and the merge cannot tell a child "
    "that failed from one that was never admitted."
)

#: What an asker is told when a plan cannot be run at all, never naming what was refused.
NOTHING_WAS_STARTED: Final = "Nothing was started: that plan cannot be run as it stands."

#: How long one specialist may take before its subtask is stated as missing. A product default;
#: the specialist's own run bounds (turns, tool calls, token budget) are tighter and apply first.
CHILD_TIMEOUT_SECONDS: Final = 300.0

#: What a subtask is assumed to cost and to take when the gate weighs a plan the system itself
#: drew, because nothing measures a subtask before it runs and no duration estimator exists. They
#: are the same for every subtask on purpose: the gate then decides on the plan's shape (how many
#: can start together, what they share, whether one is most of it) and not on a figure a model
#: could have chosen. Stated rather than hidden so a reader of a kept decision can see them.
ASSUMED_SECONDS_PER_SUBTASK: Final = 30.0
ASSUMED_TOOL_CALLS_PER_SUBTASK: Final = 2
ASSUMED_RETRIEVAL_TOKENS_PER_SUBTASK: Final = 2_000
#: What a dependent subtask re-reads of the one it depends on: its result's fields, each a short
#: value. The duplication a split would pay for one edge, counted from the contract and not typed.
COUPLING_TOKENS_PER_RESULT_FIELD: Final = 64

#: The most steps one plan may have. A plan past this is a project, and the rehearsal route holds
#: the same figure.
MOST_STEPS: Final = 12


class CoordinationError(Exception):
    """A plan or a set of parts that cannot mean what it says.

    Outside the `brain.core.errors` taxonomy, like `brain.orchestration.delegation.DelegationError`:
    nobody asking a question ever sees one, and what they are told is `NOTHING_WAS_STARTED`.
    """


# ------------------------------------------------------------------------------ the parts
class Why(enum.StrEnum):
    """Why a run's specialists ran one after another. Closed, and recorded with the run."""

    #: Fan-out was not enabled on the coordinating agent by an administrator (M18.6.2).
    FAN_OUT_NOT_ENABLED = "fan_out_not_enabled"
    #: One of the gate's six conditions did not hold (the gate's own record names which).
    GATE_DECLINED = "gate_declined"
    #: A wave would start more children together than one run may have in flight (M18.3.4).
    WAVE_OVER_THE_CAP = "wave_over_the_cap"
    #: The global parallelism budget had no room for the widest wave (M18.3.5).
    NO_ROOM = "no_room"


class Mode(enum.StrEnum):
    """How a run's specialists were run."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True)
class Coordinator:
    """The agent that hands work out, as an administrator configured it."""

    agent_id: str
    #: `brain.agents.model.entitlement_ceiling` of the coordinating agent.
    ceiling: EntitlementSet
    #: The agents an administrator allowed it to call. A subtask naming another is refused.
    callable_ids: frozenset[str]
    #: Whether an administrator let it run specialists at the same time (M18.6.2).
    may_fan_out: bool
    #: The lenses above this coordinator when it is itself somebody's specialist, root first.
    #: Empty for a coordinator the person asked directly.
    parents: tuple[Hop, ...] = ()

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            msg = "a coordinator with no agent id cannot be recorded or audited afterwards"
            raise CoordinationError(msg)

    @property
    def hop(self) -> Hop:
        return Hop(lens_id=self.agent_id, kind=LensKind.AGENT, ceiling=self.ceiling)

    @property
    def chain(self) -> tuple[Hop, ...]:
        """The lenses from the person to this coordinator, itself last."""
        return (*self.parents, self.hop)

    @property
    def depth(self) -> int:
        """How many delegations deep the coordinator already is. A person's own ask is zero."""
        return depth_of(self.chain)


@dataclass(frozen=True)
class Callee:
    """A specialist agent that could be handed a subtask, as it is loaded now."""

    agent_id: str
    tier: Tier
    #: `brain.agents.model.entitlement_ceiling` of the specialist.
    ceiling: EntitlementSet

    @property
    def hop(self) -> Hop:
        return Hop(lens_id=self.agent_id, kind=LensKind.AGENT, ceiling=self.ceiling)


@dataclass(frozen=True)
class PlanStep:
    """One subtask: who does it, what it must return, and what it needs from earlier steps."""

    subtask_id: str
    callee_id: str
    contract: SubtaskContract
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.contract.subtask_id != self.subtask_id:
            msg = (
                f"step {self.subtask_id!r} carries the contract of "
                f"{self.contract.subtask_id!r}, so its result would be checked against a "
                "promise somebody else made"
            )
            raise CoordinationError(msg)
        if not self.callee_id.strip():
            msg = f"step {self.subtask_id!r} names no specialist, so nobody can be handed it"
            raise CoordinationError(msg)


def contract_for(
    callee: Callee,
    *,
    subtask_id: str,
    objective: str,
    output: Sequence[FieldSpec],
    tool_hints: Sequence[str] = (),
) -> SubtaskContract:
    """The contract for a subtask given to this specialist, its ceiling read from the specialist.

    The capabilities are the specialist's own ceiling's, in order and once each, and the scope is
    the contract's default (no clauses), so the subtask lens narrows exactly as the specialist
    lens does. See `A_PLANNER_CHOOSES_WHO_AND_NEVER_WHAT_THEY_MAY_REACH`. A specialist whose ceiling
    names nothing gives a contract that reaches nothing, which `brain.orchestration.contract`
    refuses by its own rule that a subtask with no capability has no work to do.
    """
    seen: dict[str, Capability] = {}
    for grant in callee.ceiling.grants:
        seen.setdefault(grant.capability.value, grant.capability)
    return SubtaskContract(
        subtask_id=subtask_id,
        objective=objective,
        output=tuple(output),
        tool_hints=tuple(tool_hints),
        capabilities=tuple(seen.values()),
    )


# ------------------------------------------------------------------------------ checks
def not_allowed_sentence(subtask_id: str) -> str:
    """The one sentence for a subtask handed to an agent that may not be called or is not there."""
    return f"subtask {subtask_id!r} is handed to an agent this coordinator may not call"


def callee_refusals(
    coordinator: Coordinator, steps: Sequence[PlanStep], callees: Mapping[str, Callee]
) -> tuple[str, ...]:
    """Every step handed to an agent this coordinator may not call, one sentence each (M18.5.1).

    A step is refused when its specialist is not on the coordinator's allowed list, and also when it
    is on it and cannot be loaded (archived, disabled or gone), in the same words. See
    `A_CALLEE_THAT_IS_NOT_ALLOWED_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_REFUSAL`. A coordinator is not
    its own specialist: a plan handing a step back to the agent that made it is a loop the depth cap
    would meet at the third hop, and it is refused here before a hop is built.
    """
    return tuple(
        not_allowed_sentence(step.subtask_id)
        for step in steps
        if step.callee_id == coordinator.agent_id
        or step.callee_id not in coordinator.callable_ids
        or step.callee_id not in callees
    )


def _hops(coordinator: Coordinator, step: PlanStep, callee: Callee) -> tuple[Hop, ...]:
    """The lenses between the asker and this child: coordinator, specialist, then the subtask."""
    return child_hops(
        coordinator.chain,
        agent=callee.hop,
        subtask=Hop(
            lens_id=step.subtask_id,
            kind=LensKind.SUBTASK,
            ceiling=subtask_ceiling(step.contract),
        ),
    )


def weighed(steps: Sequence[PlanStep], callees: Mapping[str, Callee]) -> DependencyGraph:
    """The plan as the gate weighs it, with every weight produced by the system.

    The structure is the steps'. The cost of each node is `brain.ops.spend.estimate` over the
    specialist's tier and the assumed tool calls and retrieval, and the duration is the assumed one;
    what an edge shares is counted from the upstream contract's fields. Nothing a model wrote is a
    weight. See `ASSUMED_SECONDS_PER_SUBTASK`.
    """
    by_id = {one.subtask_id: one for one in steps}
    nodes = tuple(
        Node(
            subtask_id=step.subtask_id,
            cost=CostInputs(
                lane=Lane.TASK,
                tier=callees[step.callee_id].tier,
                tool_calls=max(ASSUMED_TOOL_CALLS_PER_SUBTASK, len(step.contract.tool_hints)),
                retrieval_tokens=ASSUMED_RETRIEVAL_TOKENS_PER_SUBTASK,
            ),
            seconds=ASSUMED_SECONDS_PER_SUBTASK,
        )
        for step in steps
    )
    coupling = {
        (before, step.subtask_id): len(by_id[before].contract.output)
        * COUPLING_TOKENS_PER_RESULT_FIELD
        for step in steps
        for before in step.depends_on
        if before in by_id
    }
    proposals = tuple(Proposal(one.subtask_id, one.depends_on) for one in steps)
    return graph_for(proposals, nodes, coupling)


@dataclass(frozen=True)
class Dispatch:
    """What was decided about a plan before any child starts."""

    run_id: str
    #: Why nothing may start, or empty when something may. Sentences, never a callee or a reach.
    refusals: tuple[str, ...]
    gate: GateRecord | None
    #: The steps in the order they become ready: a wave is the steps that can start together.
    waves: tuple[tuple[str, ...], ...]
    #: Why the specialists run one after another, or empty when they may run together.
    why: tuple[Why, ...]

    @property
    def refused(self) -> bool:
        return bool(self.refusals)

    @property
    def parallel(self) -> bool:
        """Whether the plan may be run in parallel, before the budget has been asked."""
        return not self.refusals and not self.why

    @property
    def widest(self) -> int:
        return max((len(wave) for wave in self.waves), default=0)


def plan_dispatch(
    *,
    run_id: str,
    coordinator: Coordinator,
    steps: Sequence[PlanStep],
    callees: Mapping[str, Callee],
    caller: EntitlementSet,
    at: datetime,
) -> Dispatch:
    """Decide, before any child starts, whether the plan may run and whether in parallel.

    In this order, and the first group that fails stops the rest, because each later check reads
    what the earlier one admitted: the specialist each step names (M18.5.1), then the plan's three
    parts agreeing and being a graph that can be run, then every child's chain (the depth cap and
    that each hop only narrows, M18.3.4), then the gate's six conditions, and last whether each wave
    is within the per-run cap. The reasons to run one after another are collected, all of them.
    """
    if not steps:
        return Dispatch(run_id, (NOTHING_WAS_STARTED,), None, (), ())
    if len(steps) > MOST_STEPS:
        return Dispatch(run_id, (NOTHING_WAS_STARTED,), None, (), ())
    unallowed = callee_refusals(coordinator, steps, callees)
    if unallowed:
        return Dispatch(run_id, unallowed, None, (), ())
    try:
        graph = weighed(steps, callees)
        proposals = tuple(Proposal(one.subtask_id, one.depends_on) for one in steps)
        plan_problems = plan_refusals(proposals, tuple(one.contract for one in steps), graph)
    except (PlanError, SpendError, ContractError) as refused:
        return Dispatch(run_id, (str(refused),), None, (), ())
    if plan_problems:
        return Dispatch(run_id, plan_problems, None, (), ())
    by_id = {one.subtask_id: one for one in steps}
    chains: list[str] = []
    try:
        for step in steps:
            hops = _hops(coordinator, step, callees[step.callee_id])
            chains.extend(
                f"subtask {step.subtask_id!r}: {one}" for one in chain_refusals(caller, hops)
            )
    except DelegationError as refused:
        return Dispatch(run_id, (str(refused),), None, (), ())
    if chains:
        return Dispatch(run_id, tuple(chains), None, (), ())
    try:
        gate = decide(run_id, graph, depth=coordinator.depth, at=at)
    except FanOutError as refused:
        return Dispatch(run_id, (str(refused),), None, (), ())
    waves = graph.waves()
    why: list[Why] = []
    if not coordinator.may_fan_out:
        why.append(Why.FAN_OUT_NOT_ENABLED)
    if not gate.parallel:
        why.append(Why.GATE_DECLINED)
    if _wave_findings(coordinator, by_id, callees, waves):
        why.append(Why.WAVE_OVER_THE_CAP)
    return Dispatch(run_id, (), gate, waves, tuple(why))


def _wave_findings(
    coordinator: Coordinator,
    by_id: Mapping[str, PlanStep],
    callees: Mapping[str, Callee],
    waves: Sequence[Sequence[str]],
) -> tuple[str, ...]:
    """Every wave that would start more children together than one run may have in flight."""
    found: list[str] = []
    for index, wave in enumerate(waves):
        together = [
            Delegation(
                run_id="wave",
                child_id=one,
                hops=_hops(coordinator, by_id[one], callees[by_id[one].callee_id]),
            )
            for one in wave
        ]
        found.extend(f"wave {index}: {one}" for one in concurrency_refusals(together))
    return tuple(found)


# ------------------------------------------------------------------------------ the ports
@dataclass(frozen=True)
class ChildWork:
    """What a specialist is handed: objective, what to return, earlier findings, and its reach."""

    run_id: str
    subtask_id: str
    callee_id: str
    objective: str
    output: tuple[FieldSpec, ...]
    tool_hints: tuple[str, ...]
    #: The asker's reach folded through the coordinator, the specialist and the subtask. The
    #: specialist runs inside it and has no way to ask for more.
    reach: EntitlementSet
    #: The ceilings of every lens between the asker and the child, root first. A specialist that
    #: resolves the asker's reach afresh before a tool call folds these into it again, so the
    #: coordinator's and the subtask's narrowing hold at every call and not only at the start.
    lenses: tuple[EntitlementSet, ...]
    #: Earlier steps' validated values by subtask id, for the steps this one depends on only.
    upstream: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class Delivered:
    """What a specialist handed back: the values, what its run cost and how long it took."""

    values: Mapping[str, object]
    minor: int = 0
    seconds: float = 0.0


class SpecialistRefusedError(Exception):
    """The specialist's reach did not cover what the subtask needed, or it was stopped."""


class Specialist(Protocol):
    """Runs one subtask inside the reach it was handed and returns values for its contract."""

    async def run(self, work: ChildWork) -> Delivered: ...


@dataclass(frozen=True)
class RoomAnswer:
    """What asking the global parallelism budget came to."""

    admitted: bool
    #: True when a halt refused it, which is the whole run's refusal and not a lack of room.
    halted: bool = False
    #: The halt's own words, or empty.
    reason: str = ""
    #: What `Rooms.give_back` is handed to free the slots. Opaque here.
    hold: object | None = None


class Rooms(Protocol):
    """The global parallelism budget, asked once and given back once."""

    async def take(self, request: AdmissionRequest) -> RoomAnswer: ...

    async def give_back(self, answer: RoomAnswer) -> None: ...


# ------------------------------------------------------------------------------ the record
class ChildStatus(enum.StrEnum):
    """What became of one child. `delivered` or one of the merge's own causes."""

    DELIVERED = "delivered"
    REFUSED = GapCause.REFUSED.value
    TIMED_OUT = GapCause.TIMED_OUT.value
    INVALID_RESULT = GapCause.INVALID_RESULT.value
    NOT_ADMITTED = GapCause.NOT_ADMITTED.value
    UNREACHABLE = GapCause.UNREACHABLE.value


@dataclass(frozen=True)
class ChildTrace:
    """One child as the trace shows it: who, how deep, what reach, what became of it, its cost."""

    subtask_id: str
    callee_id: str
    depth: int
    #: `EntitlementSet.ent_hash` of the reach the child ran at, never the reach itself.
    reach_hash: str
    status: ChildStatus
    minor: int
    seconds: float


@dataclass(frozen=True)
class Coordinated:
    """What a coordinated run came to: the decision, how it ran, each child, the merged answer."""

    run_id: str
    dispatch: Dispatch
    mode: Mode | None
    why: tuple[Why, ...]
    children: tuple[ChildTrace, ...]
    merged: MergedAnswer | None
    #: Non-empty when nothing was started, in sentences that name no agent and no capability.
    refusals: tuple[str, ...] = ()

    @property
    def started(self) -> bool:
        return self.merged is not None


# ------------------------------------------------------------------------------ the engine
@dataclass
class _Outcome:
    status: ChildStatus
    result: ValidatedResult | None = None
    minor: int = 0
    seconds: float = 0.0
    detail: str = ""


async def _child(
    run_id: str,
    step: PlanStep,
    reach: EntitlementSet,
    lenses: tuple[EntitlementSet, ...],
    upstream: Mapping[str, Mapping[str, object]],
    specialist: Specialist,
    timeout: float,
) -> _Outcome:
    """Run one child and map whatever happened to an outcome. Never raises for the child's fault."""
    work = ChildWork(
        run_id=run_id,
        subtask_id=step.subtask_id,
        callee_id=step.callee_id,
        objective=step.contract.objective,
        output=step.contract.output,
        tool_hints=step.contract.tool_hints,
        reach=reach,
        lenses=lenses,
        upstream=upstream,
    )
    began = time.monotonic()
    try:
        delivered = await asyncio.wait_for(specialist.run(work), timeout=timeout)
    except SpecialistRefusedError:
        return _Outcome(ChildStatus.REFUSED, seconds=time.monotonic() - began)
    except TimeoutError:
        return _Outcome(ChildStatus.TIMED_OUT, seconds=time.monotonic() - began)
    except Exception as failed:
        # Whatever a specialist's run raised is a subtask that produced nothing. The class is
        # logged and no message is, because a message can carry a row the specialist read.
        log.warning("specialist failed", run=run_id, error=type(failed).__name__)
        return _Outcome(ChildStatus.UNREACHABLE, seconds=time.monotonic() - began)
    elapsed = delivered.seconds if delivered.seconds > 0 else time.monotonic() - began
    problems = result_refusals(step.contract, delivered.values)
    if problems:
        return _Outcome(
            ChildStatus.INVALID_RESULT,
            minor=delivered.minor,
            seconds=elapsed,
            detail="; ".join(problems),
        )
    return _Outcome(
        ChildStatus.DELIVERED,
        result=validated(step.contract, delivered.values),
        minor=delivered.minor,
        seconds=elapsed,
    )


async def coordinate(
    *,
    run_id: str,
    coordinator: Coordinator,
    steps: Sequence[PlanStep],
    callees: Mapping[str, Callee],
    caller: EntitlementSet,
    specialist: Specialist,
    rooms: Rooms,
    traffic: TrafficClass,
    at: datetime,
    child_timeout: float = CHILD_TIMEOUT_SECONDS,
) -> Coordinated:
    """Decide, ask for room, run the specialists and merge what was checked.

    Returns a refusal with nothing started, or a run whose answer states what is missing. The
    caller keeps the decision (`Coordinated.dispatch.gate`) and the run.
    """
    dispatch = plan_dispatch(
        run_id=run_id,
        coordinator=coordinator,
        steps=steps,
        callees=callees,
        caller=caller,
        at=at,
    )
    if dispatch.refused:
        return Coordinated(run_id, dispatch, None, (), (), None, refusals=dispatch.refusals)
    why = list(dispatch.why)
    answer: RoomAnswer | None = None
    if not why:
        answer = await rooms.take(
            fan_out_request(run_id, children=dispatch.widest, traffic_class=traffic)
        )
        if answer.halted:
            return Coordinated(
                run_id,
                dispatch,
                None,
                (),
                (),
                None,
                refusals=(answer.reason or NOTHING_WAS_STARTED,),
            )
        if not answer.admitted:
            why.append(Why.NO_ROOM)
    mode = Mode.SEQUENTIAL if why else Mode.PARALLEL
    try:
        return await _run(
            run_id,
            dispatch,
            mode,
            tuple(why),
            coordinator,
            steps,
            callees,
            caller,
            specialist,
            child_timeout,
        )
    finally:
        if answer is not None:
            await rooms.give_back(answer)


async def _run(
    run_id: str,
    dispatch: Dispatch,
    mode: Mode,
    why: tuple[Why, ...],
    coordinator: Coordinator,
    steps: Sequence[PlanStep],
    callees: Mapping[str, Callee],
    caller: EntitlementSet,
    specialist: Specialist,
    child_timeout: float,
) -> Coordinated:
    by_id = {one.subtask_id: one for one in steps}
    reaches: dict[str, tuple[Hop, ...]] = {
        one.subtask_id: _hops(coordinator, one, callees[one.callee_id]) for one in steps
    }
    results: dict[str, ValidatedResult] = {}
    outcomes: dict[str, _Outcome] = {}

    async def go(step_id: str) -> None:
        step = by_id[step_id]
        upstream = {before: results[before].values for before in step.depends_on}
        outcomes[step_id] = await _child(
            run_id,
            step,
            chain_reach(caller, reaches[step_id]),
            tuple(hop.ceiling for hop in reaches[step_id]),
            upstream,
            specialist,
            child_timeout,
        )
        found = outcomes[step_id].result
        if found is not None:
            results[step_id] = found

    for wave in dispatch.waves:
        ready = [one for one in wave if all(before in results for before in by_id[one].depends_on)]
        for one in wave:
            if one not in ready:
                outcomes[one] = _Outcome(ChildStatus.NOT_ADMITTED)
        if mode is Mode.PARALLEL:
            await asyncio.gather(*(go(one) for one in ready))
        else:
            for one in ready:
                await go(one)
    return _closed(run_id, dispatch, mode, why, steps, callees, caller, reaches, outcomes, results)


def _closed(
    run_id: str,
    dispatch: Dispatch,
    mode: Mode,
    why: tuple[Why, ...],
    steps: Sequence[PlanStep],
    callees: Mapping[str, Callee],
    caller: EntitlementSet,
    reaches: Mapping[str, tuple[Hop, ...]],
    outcomes: Mapping[str, _Outcome],
    results: Mapping[str, ValidatedResult],
) -> Coordinated:
    """The trace and the merged answer, in plan order, from what each child came to."""
    gaps: list[Gap] = []
    traces: list[GapTrace] = []
    reports: list[SubtaskReport] = []
    children: list[ChildTrace] = []
    for step in steps:
        done = outcomes[step.subtask_id]
        hops = reaches[step.subtask_id]
        children.append(
            ChildTrace(
                subtask_id=step.subtask_id,
                callee_id=step.callee_id,
                depth=Delegation(run_id, step.subtask_id, hops).depth,
                reach_hash=chain_reach(caller, hops).ent_hash(),
                status=done.status,
                minor=done.minor,
                seconds=done.seconds,
            )
        )
        if done.status is not ChildStatus.NOT_ADMITTED:
            reports.append(SubtaskReport(step.subtask_id, done.minor, done.seconds))
        if done.status is ChildStatus.DELIVERED:
            continue
        gaps.append(Gap(step.subtask_id, step.contract.objective))
        traces.append(GapTrace(step.subtask_id, GapCause(done.status.value), done.detail))
    try:
        merged = merge(
            run_id,
            [results[one.subtask_id] for one in steps if one.subtask_id in results],
            reports,
            gaps=gaps,
            traces=traces,
        )
    except MergeError as refused:
        # A run whose own bookkeeping disagrees is a defect and not a result. Stated plainly.
        msg = f"run {run_id!r} could not be merged: {refused}"
        raise CoordinationError(msg) from refused
    return Coordinated(run_id, dispatch, mode, why, tuple(children), merged)
