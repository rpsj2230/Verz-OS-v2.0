"""Weighing a multi-agent plan before any agent runs: the fan-out gate, the contracts and the merge,
over HTTP, with the decision kept.

`brain.orchestration` is a package of refusals nothing called: a plan's weighted graph, the six
conditions that decide whether it is split, a contract for what each subtask returns, and a merge
that states a gap where a subtask failed. This is the first thing that asks them, and it asks them
of a plan an administrator writes down rather than of a run, because **the coordinating agent that
would produce a plan and dispatch its children does not exist** (M18.5). So this is the
deterministic half of an orchestrator made reachable, and a rehearsal of it, and it starts nothing.

**The planner's shape and the system's weights stay apart.** A subtask's structure (what it depends
on) is read through `plan.read_proposal`, the checks a model's proposal will one day pass, and its
weight is **produced by `brain.ops.spend.estimate` from a lane, a tier, a tool count and a retrieval
size**, never typed in as a token figure. Only the duration is the administrator's, because no
duration estimator exists, and the page says so. Rejected: a body carrying a cost per subtask,
which would let a rehearsal pass the gate with whatever number made it pass and teach nobody what
the gate is for.

**A plan that is not one is refused before the gate runs, and nothing is recorded for it.** A
dependency on a subtask that is not in the plan, a cycle, and a dependency with no measured coupling
are each refused by the graph in its own words (`plan.graph_for`), because a gate deciding over a
plan smaller than the one that would run is a decision about nothing. `plan.plan_refusals`, which
compares a proposal, the contracts and the graph, is not asked here: all three are read from the one
list of subtasks, so they agree by construction, and it belongs to the day a planner's proposal
arrives from a model on its own (M18.5.3).

**The decision is kept, and only its numbers.** `ops.fanout_gate` (`0240`) holds the five inputs,
the conditions evaluated and failed, and the verdict, with who asked. No objective, no subtask name.
`SINGLE_LOOP` is the default and is not a refusal: a plan that fails a condition is still a plan,
and the record says which conditions it failed so the plan can be reshaped.

**Results are merged only after they are checked.** Where a rehearsal supplies what each subtask
returned, each is validated against its contract (`contract.validated_or_none`), a failure becomes a
stated gap and never a merge input, and the merge names what is missing. A subtask nothing was
supplied for is a gap for a different cause. Per-subtask cost and duration are in the answer, and
the total is the sum of the rows shown.

**One authority, held over everything**, `admin:agent_lifecycle`: a plan is about how agents are
used across the install, and the gate is install-wide. The switch gates writing a rehearsal and not
reading the decisions already kept.

**Not claimed:** the coordinating agent, a planner that asks a model (M18.5.3), specialists
(M18.5.2), the callee allow-list (M18.5.1), the global parallelism budget (M18.3.5) and the depth
and concurrency caps at dispatch (M18.3.4, which the gate's conditions only mirror).

Task ids: M18.1.3, M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Final, Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.lane import Lane
from brain.locale import currency_or_unset
from brain.models.routing import Tier
from brain.ops import fanout_gate_store
from brain.ops.features import ORCHESTRATION_REHEARSAL, is_on
from brain.ops.spend import CostInputs, SpendError
from brain.orchestration.contract import (
    ContractError,
    FieldKind,
    FieldSpec,
    SubtaskContract,
    ValidatedResult,
    result_refusals,
    validated,
)
from brain.orchestration.fanout import GateRecord, decide
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
    graph_for,
    read_proposal,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: Reads the decisions kept and weighs a plan. Held over everything or not at all.
REHEARSAL_AUTHORITY: Final = AGENT_LIFECYCLE_CAPABILITY

#: The most subtasks and dependencies one rehearsal may describe. A plan past these is a project.
MOST_SUBTASKS: Final = 12
MOST_DEPENDENCIES: Final = 40

#: What the page says about the numbers an administrator types.
THE_ESTIMATOR_PRODUCES_EVERY_WEIGHT_BUT_THE_DURATION: Final = (
    "Each subtask's size is estimated by the product from its tier, its tool calls and what it "
    "reads, and what two subtasks share is the coupling you give. The duration is your estimate, "
    "because nothing measures one yet."
)


def may_rehearse(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may weigh a plan and read the decisions kept: the authority, over
    everything."""
    return _in_reach(reach, REHEARSAL_AUTHORITY, NOWHERE, now)


# ------------------------------------------------------------------------------- the body
class PromisedFieldAsked(BaseModel):
    """One field a subtask promises to return. A name and one of the six kinds; never prose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=64)]
    kind: Literal["identifier", "label", "integer", "decimal", "boolean", "timestamp"]


class SubtaskAsked(BaseModel):
    """One subtask: its structure, what it returns, and what the estimator needs to size it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subtask_id: Annotated[str, Field(min_length=1, max_length=64)]
    objective: Annotated[str, Field(min_length=1, max_length=240)]
    depends_on: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=MOST_SUBTASKS
    )
    output: list[PromisedFieldAsked] = Field(min_length=1, max_length=16)
    capabilities: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=16
    )
    tier: Literal["small", "main", "heavy"] = "main"
    tool_calls: Annotated[int, Field(ge=0, le=100)] = 0
    retrieval_tokens: Annotated[int, Field(ge=0, le=200_000)] = 0
    #: The administrator's own estimate of the wall-clock time. Strictly positive.
    seconds: Annotated[float, Field(gt=0, le=3600)]


class CouplingAsked(BaseModel):
    """What two dependent subtasks share, in tokens a split would duplicate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    before: Annotated[str, Field(min_length=1, max_length=64)]
    after: Annotated[str, Field(min_length=1, max_length=64)]
    tokens: Annotated[int, Field(ge=0, le=1_000_000)]


class ReturnedAsked(BaseModel):
    """What one subtask returned in the rehearsal, and what it cost."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subtask_id: Annotated[str, Field(min_length=1, max_length=64)]
    values: dict[str, Any]
    minor: Annotated[int, Field(ge=0, le=100_000_000)] = 0
    seconds: Annotated[float, Field(ge=0, le=3600)] = 0


class RehearsalAsked(BaseModel):
    """A plan, how deep the run already is, and optionally what each subtask returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    depth: Annotated[int, Field(ge=0, le=2)] = 0
    subtasks: list[SubtaskAsked] = Field(min_length=1, max_length=MOST_SUBTASKS)
    coupling: list[CouplingAsked] = Field(default_factory=list, max_length=MOST_DEPENDENCIES)
    returned: list[ReturnedAsked] = Field(default_factory=list, max_length=MOST_SUBTASKS)


# ----------------------------------------------------------------------------- the answer
class GateView(BaseModel):
    """What the gate was given and decided. Numbers, the conditions and a word."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    decided_at: datetime
    decided_by: str | None
    branches: int
    depth: int
    cost_multiplier: float
    speedup: float
    largest_share: float
    evaluated: list[str]
    failed: list[str]
    #: `single_loop` or `parallel`. Single loop is the default and not a refusal.
    verdict: str


class SubtaskCostView(BaseModel):
    """What one subtask cost and how long it took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subtask_id: str
    minor: int
    seconds: float


class MergedView(BaseModel):
    """What the merge wrote: each subtask's checked values, its cost, and what is missing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: dict[str, dict[str, Any]]
    reports: list[SubtaskCostView]
    #: The sum of the rows above, never a figure carried beside them.
    total_minor: int
    #: The unit of every figure above: the install's currency, or `XXX` when it has chosen none
    #: (`brain.report_routes.A_FIGURE_SAYS_ITS_CURRENCY_AND_ITS_CLOCK`).
    currency: str
    complete: bool
    #: What is missing, in words, or empty when nothing is.
    notice: str


class PlanWeighedView(BaseModel):
    """One rehearsal: what the gate decided and what was merged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    gate: GateView
    #: Null unless results were handed in.
    merged: MergedView | None
    #: True while no coordinating agent exists to dispatch the children this rehearses.
    nothing_is_started: bool = True


class DecisionsPage(BaseModel):
    """The decisions kept, newest first, and whether weighing a plan is switched on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decisions: list[GateView]
    rehearsal_is_on: bool
    #: How the weights are produced, so the page says it only while it is true.
    weights_note: str = THE_ESTIMATOR_PRODUCES_EVERY_WEIGHT_BUT_THE_DURATION


def gate_view(record: GateRecord, by: str | None) -> GateView:
    return GateView(
        run_id=record.run_id,
        decided_at=record.at,
        decided_by=by,
        branches=record.inputs.branches,
        depth=record.inputs.depth,
        cost_multiplier=record.inputs.cost_multiplier,
        speedup=record.inputs.speedup,
        largest_share=record.inputs.largest_share,
        evaluated=[one.value for one in record.evaluated],
        failed=[one.value for one in record.failed],
        verdict=record.verdict.value,
    )


# -------------------------------------------------------------------------- the machinery
def _not_answerable() -> Absent:
    return Absent("the orchestration screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    message = f"that plan was not weighed: {reason}"
    return Absent(message, public_message=message)


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def contracts_of(body: RehearsalAsked) -> tuple[SubtaskContract, ...]:
    """The contract each subtask declares, refused in the package's own words when one is not."""
    try:
        return tuple(
            SubtaskContract(
                subtask_id=one.subtask_id,
                objective=one.objective,
                output=tuple(FieldSpec(name=f.name, kind=FieldKind(f.kind)) for f in one.output),
                capabilities=tuple(Capability(value=c) for c in one.capabilities),
            )
            for one in body.subtasks
        )
    except ContractError as refused:
        raise _refused_because(str(refused)) from None


def graph_of(body: RehearsalAsked) -> DependencyGraph:
    """The weighted graph of the plan, refused in the graph's own words when it is not one.

    The structure goes through `read_proposal`, the check a model's proposal will pass, and every
    weight but the duration is produced by `spend.estimate` through `Node`, never taken from the
    body.
    """
    try:
        proposals = read_proposal(
            [{"subtask_id": one.subtask_id, "depends_on": one.depends_on} for one in body.subtasks]
        )
        nodes = tuple(
            Node(
                subtask_id=one.subtask_id,
                cost=CostInputs(
                    lane=Lane.ANSWER,
                    tier=Tier(one.tier),
                    tool_calls=one.tool_calls,
                    retrieval_tokens=one.retrieval_tokens,
                ),
                seconds=one.seconds,
            )
            for one in body.subtasks
        )
        coupling = {(one.before, one.after): one.tokens for one in body.coupling}
        return graph_for(proposals, nodes, coupling)
    except (PlanError, SpendError) as refused:
        raise _refused_because(str(refused)) from None


def merged_view(answer: MergedAnswer, ids: frozenset[str]) -> MergedView:
    return MergedView(
        values={
            key: {k: _plain(v) for k, v in held.items()} for key, held in answer.values.items()
        },
        reports=[
            SubtaskCostView(subtask_id=one.subtask_id, minor=one.minor, seconds=one.seconds)
            for one in answer.reports
        ],
        total_minor=answer.total_minor,
        currency=currency_or_unset(),
        complete=answer.is_complete,
        notice=answer.notice(disclosable=ids),
    )


def _plain(value: object) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def merged_of(
    run_id: str, body: RehearsalAsked, contracts: tuple[SubtaskContract, ...]
) -> MergedAnswer:
    """What the merge writes from the results handed in, with a stated gap for each that failed.

    Each is checked against its contract first, and one that does not satisfy it is a gap and never
    an input; a subtask nothing was handed in for is a gap for a different cause.
    """
    handed = {one.subtask_id: one for one in body.returned}
    unknown = sorted(set(handed) - {one.subtask_id for one in contracts})
    if unknown:
        raise _refused_because(
            f"results were handed in for {unknown}, which the plan does not describe"
        )
    results: list[ValidatedResult] = []
    reports: list[SubtaskReport] = []
    gaps: list[Gap] = []
    traces: list[GapTrace] = []
    for contract in contracts:
        given = handed.get(contract.subtask_id)
        if given is None:
            gaps.append(Gap(subtask_id=contract.subtask_id, objective=contract.objective))
            traces.append(GapTrace(subtask_id=contract.subtask_id, cause=GapCause.NOT_ADMITTED))
            continue
        values = {
            spec.name: _read_timestamp(spec, given.values.get(spec.name))
            for spec in contract.output
            if spec.name in given.values
        } | {name: v for name, v in given.values.items() if name not in contract.field_names}
        reports.append(
            SubtaskReport(subtask_id=contract.subtask_id, minor=given.minor, seconds=given.seconds)
        )
        if result_refusals(contract, values):
            gaps.append(Gap(subtask_id=contract.subtask_id, objective=contract.objective))
            traces.append(GapTrace(subtask_id=contract.subtask_id, cause=GapCause.INVALID_RESULT))
            continue
        results.append(validated(contract, values))
    try:
        return merge(run_id, results, reports, gaps=gaps, traces=traces)
    except MergeError as refused:
        raise _refused_because(str(refused)) from None


def _read_timestamp(spec: FieldSpec, value: object) -> object:
    """A timestamp arrives as ISO text in JSON and is read as one, or left as it was."""
    if spec.kind is FieldKind.TIMESTAMP and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


router = APIRouter(prefix=API_PREFIX, tags=["orchestration"])


@router.get(
    "/orchestration/weighed-plans", response_model=DecisionsPage, responses=COMMON_RESPONSES
)
async def decisions(request: Request, asked: Asked) -> DecisionsPage:
    """The decisions the gate has kept, newest first, for a caller who may weigh a plan."""
    if not may_rehearse(asked.reach, asked.now):
        log.info("orchestration screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        kept = await fanout_gate_store.recent(session)
        switched = await is_on(session, ORCHESTRATION_REHEARSAL)
    return DecisionsPage(
        decisions=[gate_view(one.record, one.by) for one in kept], rehearsal_is_on=switched
    )


@router.post(
    "/orchestration/weighed-plans",
    status_code=201,
    response_model=PlanWeighedView,
    responses=COMMON_RESPONSES,
)
async def rehearse(request: Request, body: RehearsalAsked, asked: Asked) -> PlanWeighedView:
    """Weigh a plan, keep how the gate decided, and merge what was handed in.

    The authority, then the switch, then the plan, in that order: a caller without the authority
    learns nothing, and one with it is told the switch is off before anything about the plan.
    """
    if not may_rehearse(asked.reach, asked.now):
        log.info("plan not weighed: refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    run_id = f"rehearsal-{uuid.uuid4().hex[:16]}"
    async with _require_sessions(request)() as session:
        if not await is_on(session, ORCHESTRATION_REHEARSAL):
            raise _refused_because(
                "weighing a plan is switched off for this install; switch it on from Features"
            )
        contracts = contracts_of(body)
        graph = graph_of(body)
        record = decide(run_id, graph, depth=body.depth, at=asked.now)
        await fanout_gate_store.keep(session, record, by=asked.caller.principal.id)
        merged = None
        if body.returned:
            merged = merged_view(
                merged_of(run_id, body, contracts), frozenset(one.subtask_id for one in contracts)
            )
        await session.commit()
    log.info(
        "plan weighed",
        run=run_id,
        verdict=record.verdict.value,
        principal=asked.caller.principal.id,
    )
    return PlanWeighedView(
        run_id=run_id,
        gate=gate_view(record, asked.caller.principal.id),
        merged=merged,
    )
