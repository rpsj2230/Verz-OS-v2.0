"""A coordinating agent, over HTTP: who it may call, whether it may fan out, and running a request.

`brain.orchestration.coordinator` holds the rules of a coordinating agent and nothing could reach
them: no screen set which agents an agent may hand a subtask to, no switch let it run them together,
and no route asked a model to split a request. This is the door. It orders the questions, loads the
agents, and adds no rule of its own about what a child may reach.

**What a coordinator may call is an administrator's decision, made on the coordinator and read by
nobody who does not answer for it.** Allowing a callee, withdrawing one and letting an agent fan out
are the lifecycle authority over the coordinator's row, which is its department's administrator, and
a missing agent, a hidden one and one outside the caller's authority are the one 404. The callee has
to be an agent the caller can see, so an administrator cannot name an agent they could not find, and
a personal agent is refused as a callee because it is found by its owner and by nobody else.
**Neither decision confers reach**: a link only says who may be asked, and what the specialist then
touches is the asker's reach narrowed by both agents and the subtask. See
`LINKING_TWO_AGENTS_IS_CONFIGURATION_AND_CONFERS_NO_REACH`.

**The names beside a coordinator are told to those who answer for it, and only the agents the
reader could see anyway.** A reader who is the coordinator's steward or holds the authority is shown
the specialists it may call, minus any the reader cannot see; anybody else is shown a view with no
list and no sign that a list exists, so the answer is the same whether an agent has links or not.
See `ONLY_THOSE_WHO_ANSWER_FOR_AN_AGENT_ARE_TOLD_WHO_IT_MAY_CALL`.

**Running is anybody who may start the coordinator, at their own reach, behind a switch that ships
off.** The asker's words go to a model to be split into subtasks, so nothing runs while
`multi_agent_coordination` is off. Then the order is fixed and each step stops the rest: the agent
is one the asker may start, it has specialists, the request is not blank, a model is set up, the
model's reply passes `brain.orchestration.planner.read_plan`, and the plan passes `plan_dispatch`. A
refusal at any of them starts nothing and is one sentence that names no agent and no capability. See
`NOTHING_RUNS_UNTIL_THE_PLAN_HAS_PASSED_EVERY_CHECK`.

**Each specialist is asked by the function that answers a person, at the reach the engine folded.**
`brain.api_routes.answered_for` runs the specialist's own loop, so its tool calls are judged at its
reach, leashed and recorded as any agent's are, and the lenses above it ride on the question so they
narrow every tool call and not only the first (`brain.api_routes.Answering.lenses`). What comes back
is read as values by `brain.orchestration.specialist` and checked against the contract.

**What a specialist cost is the estimate for its tier, and the page says so.** `answered_for`
records its own spend by trace, and joining that to a subtask is a leaf of its own (M17.4.6), so
each child is charged `brain.ops.spend.estimate` of its tier and the answer carries
`COSTS_ARE_ESTIMATES_UNTIL_A_RUN_IS_JOINED_TO_ITS_SPEND` rather than a figure that reads as
measured. The seconds are measured.

**The decision and the run are kept without what was asked.** The gate's record goes to
`ops.fanout_gate` as a rehearsal's does, and the run to `ops.coordinated_run`: how the specialists
were run, why not together, and one line per child with a status, a depth, a reach hash and a cost.
No request, objective or result value is written.

Task ids: M18.1.1, M18.5.1, M18.5.3, M18.6.2
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_audience_routes import answers_for
from brain.agent_coauthor_routes import _spent
from brain.agent_lifecycle_routes import _actionable, _not_changed, holds
from brain.agent_routes import (
    _require_session_factory,
    _visible_record,
    one_agent,
    record_of,
    viewer_of,
)
from brain.agents import coordination_store
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.agents.model import (
    AgentRecord,
    entitlement_ceiling,
    runnable_agent_ids,
    visible_agent_ids,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Answering, Asked, Asking, Question, answered_for, capacity_ledger_of
from brain.core.errors import Absent, Failed
from brain.core.lane import Lane
from brain.gate.answer import Answered
from brain.gate.context import Channel, TrafficClass, open_trace
from brain.knowledge.visibility import Visibility
from brain.models.disclosure import DataCategory
from brain.models.driver import DriverMessage, DriverResponse, ProviderUnavailable
from brain.models.metering import Meter
from brain.models.routing import NoCompliantRoute, Tier
from brain.ops import coordinated_run_store, fanout_gate_store
from brain.ops.admission import AdmissionRequest, CapacityState
from brain.ops.capacity_ledger import Hold
from brain.ops.features import is_on
from brain.ops.features_declared.multi_agent_coordination import MULTI_AGENT_COORDINATION
from brain.ops.halt import NOTHING_HALTED, HaltState
from brain.ops.halt_store import read_state
from brain.ops.model_service import ModelService
from brain.ops.spend import CostInputs, estimate
from brain.ops.tuning import configured_budgets
from brain.orchestration.coordinator import (
    NOTHING_WAS_STARTED,
    Callee,
    ChildWork,
    Coordinated,
    Coordinator,
    RoomAnswer,
    coordinate,
)
from brain.orchestration.delegation import may_fan_out
from brain.orchestration.planner import (
    PLANNER_TIER,
    REPLY_TOKENS,
    Offered,
    PlanRefusedError,
    checked_request,
    planner_messages,
    read_plan,
)
from brain.orchestration.specialist import Answer, AskingSpecialist
from brain.orchestration_routes import (
    GateView,
    MergedView,
    gate_view,
    may_rehearse,
    merged_view,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why linking two agents is not a grant.
LINKING_TWO_AGENTS_IS_CONFIGURATION_AND_CONFERS_NO_REACH: Final = (
    "Allowing an agent to hand a subtask to another is configuration made by whoever can edit "
    "agents. It says who may be asked and nothing about what they can touch: that is the asker's "
    "own access, narrowed by both agents and by the subtask. A link that widened anything would "
    "make linking two agents a grant, which is a different act with a different approver."
)

#: Why the names beside a coordinator are told to few.
ONLY_THOSE_WHO_ANSWER_FOR_AN_AGENT_ARE_TOLD_WHO_IT_MAY_CALL: Final = (
    "Which specialists a coordinator may call is told to its steward and to a holder of the "
    "lifecycle authority over its row, and only the agents the reader could see anyway. Anybody "
    "else is shown a view with no list and nothing that says whether a list exists."
)

#: Why nothing runs until every check has passed.
NOTHING_RUNS_UNTIL_THE_PLAN_HAS_PASSED_EVERY_CHECK: Final = (
    "The agent is one the asker may start, it has specialists, the request is not blank, a model "
    "is set up, the model's reply passes the planner's reading, and the plan passes the dispatch "
    "checks, in that order. A refusal at any of them starts nothing."
)

#: What a cost on this page is until a run is joined to its recorded spend.
COSTS_ARE_ESTIMATES_UNTIL_A_RUN_IS_JOINED_TO_ITS_SPEND: Final = (
    "Each specialist is charged the product's estimate for its model tier. What each one actually "
    "spent is recorded against its own request and is not yet joined to this run, so the figures "
    "here are estimates. The seconds are measured."
)

#: What an administrator is told, one sentence for each refusal.
NOT_SWITCHED_ON: Final = (
    "Nothing was started: handing work between agents is not switched on for this company yet."
)
NO_SPECIALISTS_HERE: Final = (
    "Nothing was started: this agent has not been allowed to hand work to any other agent."
)
NO_MODEL_HERE: Final = (
    "Nothing was started: no model is set up on this install yet, so the request cannot "
    "be split up."
)
NO_ANSWER_NOW: Final = (
    "Nothing was started: the request could not be split up just now. Try again in a moment."
)
NO_AGENT_TO_CALL: Final = "Nothing was changed: that agent cannot be allowed here."
A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER: Final = (
    "Nothing was changed: a personal agent is found only by the person it belongs to, so it "
    "cannot be handed work for somebody else."
)
AN_AGENT_DOES_NOT_CALL_ITSELF: Final = "Nothing was changed: an agent cannot hand work to itself."
TOO_MANY_SPECIALISTS: Final = "Nothing was changed: this agent may call as many agents as it can."
NOTHING_TO_WITHDRAW: Final = "Nothing was changed: it was not allowed to call that agent."
THE_PLAN_COULD_NOT_BE_USED: Final = (
    "Nothing was started: the plan that was drawn up for that request could not be used."
)

#: Words an act's refusal carries as `outcome`.
REFUSED: Final = "refused"
UNAVAILABLE: Final = "unavailable"

#: The most agents one coordinator may be allowed to call, so a card stays a list a person reads.
MAX_SPECIALISTS: Final = 24

#: A run's cost on the page: the product's estimate for a specialist's tier, with two tool calls and
#: a modest retrieval. Held with `brain.orchestration.coordinator`'s assumed figures.
ESTIMATED_TOOL_CALLS: Final = 2

# ------------------------------------------------------------------------ the figures
COORDINATION_PATH: Final = "/agents/{agent_id}/coordination"
CALLEES_PATH: Final = "/agents/{agent_id}/coordination/callees"
CALLEE_REMOVALS_PATH: Final = "/agents/{agent_id}/coordination/callees/removals"
FAN_OUT_PATH: Final = "/agents/{agent_id}/coordination/fan-out"
RUNS_PATH: Final = "/orchestration/coordinated-runs"


# ------------------------------------------------------------------------------ the views
class CalleeAsked(BaseModel):
    """One agent, by the slug the install knows it by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    callee_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+$")]


class FanOutAsked(BaseModel):
    """Whether an agent may run its specialists at the same time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool


class CalleeView(BaseModel):
    """One agent a coordinator may hand a subtask to, by the name its administrator gave it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class CoordinationView(BaseModel):
    """What a coordinator may call and whether it may fan out, as this reader may be told it.

    `callees` is empty and `names_shown` false for a reader who does not answer for the agent, and
    nothing else in the body varies with what was stored, so such a reader cannot tell a
    coordinator with no specialists from one with many.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    names_shown: bool
    callees: list[CalleeView] = []
    fan_out_enabled: bool = False
    may_change: bool
    #: Whether handing work between agents is switched on for this install.
    switched_on: bool
    #: What a link is and is not, said once by the route.
    words: str = LINKING_TWO_AGENTS_IS_CONFIGURATION_AND_CONFERS_NO_REACH


class RunAsked(BaseModel):
    """The coordinating agent to ask, and the request to split between its specialists."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    coordinator_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+$")]
    ask: Annotated[str, Field(min_length=1, max_length=4_000)]


class ChildView(BaseModel):
    """What became of one subtask: who did it, how deep, and the word for how it ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subtask_id: str
    callee_id: str
    depth: int
    status: str
    seconds: float


class CoordinatedRunView(BaseModel):
    """One coordinated run: how it ran and why not together, the gate, the children, the answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    #: `parallel` or `sequential`.
    mode: str
    #: Why the specialists were not run together, or empty when they were.
    why: list[str]
    gate: GateView | None
    children: list[ChildView]
    merged: MergedView
    #: Said once: the figures in `merged` are estimates.
    cost_note: str = COSTS_ARE_ESTIMATES_UNTIL_A_RUN_IS_JOINED_TO_ITS_SPEND


class KeptChildView(BaseModel):
    """One child of a kept run, as an administrator reads the trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subtask_id: str
    callee_id: str
    depth: int
    reach_hash: str
    status: str
    cost_minor: int
    seconds: float


class KeptRunView(BaseModel):
    """A run that was kept: how it went, never what it was about."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    coordinator_id: str
    started_at: datetime
    asked_by: str
    mode: str
    why: list[str]
    children: list[KeptChildView]
    complete: bool
    total_minor: int
    #: The unit of every figure above: the install's currency, or `XXX` when it has chosen none.
    currency: str


class KeptRunsPage(BaseModel):
    """The runs kept, newest first, and whether running one is switched on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: list[KeptRunView]
    switched_on: bool


# ------------------------------------------------------------------------------ the store
class Coordination(Protocol):
    """What one install keeps about who may call whom, in a form a test can hold in memory."""

    async def callees(self, agent_id: str) -> tuple[str, ...]: ...

    async def fan_out(self, agent_id: str) -> bool: ...

    async def allow(self, *, coordinator_id: str, callee_id: str, by: str) -> bool: ...

    async def withdraw(self, *, coordinator_id: str, callee_id: str, by: str) -> bool: ...

    async def set_fan_out(self, *, agent_id: str, enabled: bool, by: str) -> bool: ...


class StoredCoordination:
    """`Coordination` over `agent.agent_callee` and `agent.agent_fanout`, in the caller's name."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def callees(self, agent_id: str) -> tuple[str, ...]:
        async with self._sessions() as session:
            return await coordination_store.callees_of(session, agent_id)

    async def fan_out(self, agent_id: str) -> bool:
        async with self._sessions() as session:
            return await coordination_store.fan_out_enabled(session, agent_id)

    async def allow(self, *, coordinator_id: str, callee_id: str, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await coordination_store.add_callee(
                session, coordinator_id=coordinator_id, callee_id=callee_id, by=by
            )

    async def withdraw(self, *, coordinator_id: str, callee_id: str, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await coordination_store.remove_callee(
                session, coordinator_id=coordinator_id, callee_id=callee_id, by=by
            )

    async def set_fan_out(self, *, agent_id: str, enabled: bool, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await coordination_store.set_fan_out(
                session, agent_id=agent_id, enabled=enabled, by=by
            )


def coordination_of(request: Request) -> Coordination:
    """`app.state.agent_coordination` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_coordination", None)
    if found is not None:
        # A cast at the seam a test fills: whatever is put on `app.state` is held to this protocol
        # by the tests that put it there, and a runtime check would add nothing.
        return cast(Coordination, found)
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredCoordination(factory)


async def coordination_is_on(request: Request) -> bool:
    """Whether a request may be split between agents on this install. Off until it is turned on.

    `app.state.multi_agent_coordination_on` wins when something put a boolean there, as every other
    switch read here does, so a test can say it without a database.
    """
    found = getattr(request.app.state, "multi_agent_coordination_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, MULTI_AGENT_COORDINATION)


# ------------------------------------------------------------------------------ the model
class PlannerCalls(Protocol):
    """What the planning call needs of `brain.models.calls.ModelCalls.complete`, narrowed."""

    async def complete(
        self,
        messages: tuple[DriverMessage, ...],
        *,
        lane: Lane,
        meter: Meter,
        trace_id: str,
        tier: Tier | None = None,
        max_output_tokens: int | None = None,
        categories: tuple[DataCategory, ...] = (),
    ) -> DriverResponse: ...


def planner_calls_of(request: Request) -> PlannerCalls | None:
    """`app.state.planner_calls` when a test put one there, the executor otherwise, or None.

    None on a process with no model service, which the route says in words and never as a failure.
    """
    found: PlannerCalls | None = getattr(request.app.state, "planner_calls", None)
    if found is not None:
        return found
    service = getattr(request.app.state, "models", None)
    return service.calls if isinstance(service, ModelService) else None


# ------------------------------------------------------------------------------ the machinery
router = APIRouter(prefix=API_PREFIX, tags=["orchestration"])

_TOLD: Final = {**COMMON_RESPONSES}


def _trace_id() -> str:
    import structlog.contextvars

    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _agent_named(
    session: AsyncSession, agent_id: str, asked: Asking
) -> tuple[AgentRecord, bool] | None:
    """The agent and whether this reader can see it, or None when there is no such agent."""
    row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
    record = record_of(row) if row is not None else None
    if record is None:
        return None
    return record, agent_id in visible_agent_ids((record,), viewer_of(asked))


async def _present(request: Request, record: AgentRecord, asked: Asking) -> CoordinationView:
    """The view of one agent for this reader, reading only what this reader may be told."""
    store = coordination_of(request)
    answering = answers_for(record, asked)
    shown: list[CalleeView] = []
    fan = False
    if answering:
        fan = await store.fan_out(record.agent_id)
        factory = _require_session_factory(request)
        async with factory() as session:
            for callee_id in await store.callees(record.agent_id):
                found = await _agent_named(session, callee_id, asked)
                if found is not None and found[1]:
                    shown.append(CalleeView(agent_id=callee_id, display_name=found[0].display_name))
    return CoordinationView(
        agent_id=record.agent_id,
        names_shown=answering,
        callees=shown,
        fan_out_enabled=fan,
        may_change=holds(AGENT_LIFECYCLE_CAPABILITY, record, asked),
        switched_on=await coordination_is_on(request),
    )


@router.get(COORDINATION_PATH, response_model=CoordinationView, responses=COMMON_RESPONSES)
async def agent_coordination(request: Request, agent_id: str, asked: Asked) -> CoordinationView:
    """What one agent may call and whether it may fan out, or the answer a missing agent gets."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    return await _present(request, record, asked)


@router.post(CALLEES_PATH, response_model=CoordinationView, responses=_TOLD)
async def allow_callee(
    request: Request, agent_id: str, body: CalleeAsked, asked: Asked
) -> CoordinationView | JSONResponse:
    """Allow one agent to hand subtasks to another, in the caller's name. Allowing what is allowed
    is the same answer, so a second press is not a second row.

    The callee has to be an agent the caller can see, and not the coordinator itself or a personal
    agent. A caller who may act and may not do this is told why in one sentence and writes nothing.
    """
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    record = found.record
    if body.callee_id == record.agent_id:
        return _not_changed(REFUSED, AN_AGENT_DOES_NOT_CALL_ITSELF)
    factory = _require_session_factory(request)
    async with factory() as session:
        callee = await _agent_named(session, body.callee_id, asked)
    if callee is None or not callee[1]:
        return _not_changed(REFUSED, NO_AGENT_TO_CALL)
    if callee[0].audience.level is Visibility.PERSONAL:
        return _not_changed(REFUSED, A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER)
    store = coordination_of(request)
    if len(await store.callees(record.agent_id)) >= MAX_SPECIALISTS:
        return _not_changed(REFUSED, TOO_MANY_SPECIALISTS)
    await store.allow(
        coordinator_id=record.agent_id, callee_id=body.callee_id, by=asked.caller.principal.id
    )
    log.info("callee allowed", agent=record.agent_id, principal=asked.caller.principal.id)
    return await _present(request, record, asked)


@router.post(CALLEE_REMOVALS_PATH, response_model=CoordinationView, responses=_TOLD)
async def withdraw_callee(
    request: Request, agent_id: str, body: CalleeAsked, asked: Asked
) -> CoordinationView | JSONResponse:
    """Withdraw a link, in the caller's name. The row stays. Needs no sight of the callee, so a
    link to an agent since made invisible can still be taken back."""
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    done = await coordination_of(request).withdraw(
        coordinator_id=found.record.agent_id,
        callee_id=body.callee_id,
        by=asked.caller.principal.id,
    )
    if not done:
        return _not_changed(REFUSED, NOTHING_TO_WITHDRAW)
    log.info("callee withdrawn", agent=found.record.agent_id, principal=asked.caller.principal.id)
    return await _present(request, found.record, asked)


@router.post(FAN_OUT_PATH, response_model=CoordinationView, responses=_TOLD)
async def set_fan_out(
    request: Request, agent_id: str, body: FanOutAsked, asked: Asked
) -> CoordinationView:
    """Let an agent run its specialists at the same time, or take that back, in the caller's name.

    Setting what is already set is the same answer. It is not behind the switch: it is
    configuration, and what the switch gates is running a request.
    """
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    await coordination_of(request).set_fan_out(
        agent_id=found.record.agent_id, enabled=body.enabled, by=asked.caller.principal.id
    )
    log.info(
        "fan-out set",
        agent=found.record.agent_id,
        enabled=body.enabled,
        principal=asked.caller.principal.id,
    )
    return await _present(request, found.record, asked)


# ----------------------------------------------------------------------------- the ports
class LedgerRooms:
    """The global parallelism budget over the install's cache, or over the caller's own count.

    One take for the widest wave and one give-back, as `brain.orchestration.coordinator` asks. Where
    there is no cache the budget is decided over an empty count, which admits: the per-run cap
    and the gate's conditions bound the fan-out without it, and refusing every fan-out because a
    cache is not configured would take the feature away from an install that never wanted one.
    """

    def __init__(self, request: Request, *, now: datetime, halts: HaltState) -> None:
        self._ledger = capacity_ledger_of(request.app.state)
        self._now = now
        self._halts = halts

    async def take(self, request: AdmissionRequest) -> RoomAnswer:
        budgets = configured_budgets()
        if self._ledger is None:
            decision = may_fan_out(
                request, budgets, CapacityState(), now=self._now, halts=self._halts
            )
            return RoomAnswer(
                admitted=decision.admitted,
                halted=decision.halted,
                reason=decision.reason if decision.halted else "",
            )
        taken = await asyncio.to_thread(
            self._ledger.admit,
            request,
            budgets,
            now=self._now,
            fallback=CapacityState(),
            halts=self._halts,
        )
        return RoomAnswer(
            admitted=taken.admitted,
            halted=taken.decision.halted,
            reason=taken.decision.reason if taken.decision.halted else "",
            hold=taken.hold,
        )

    async def give_back(self, answer: RoomAnswer) -> None:
        hold = answer.hold
        if self._ledger is not None and isinstance(hold, Hold):
            await asyncio.to_thread(self._ledger.give_back, hold)


def _asking_the_specialist(request: Request, asked: Asking, run_id: str) -> Any:
    """A function that puts a subtask to its specialist as a question at the folded reach."""
    base = Answering.of(asked)

    async def ask(work: ChildWork, question: str) -> Answer:
        began = time.monotonic()
        try:
            put = Question(question=question, agent=work.callee_id)
        except ValidationError:
            return Answer(text=None, refused=True)
        outcome = await answered_for(
            request,
            open_trace(f"{run_id}-{work.subtask_id}", asked.now, asked.channel),
            dataclasses.replace(base, reach=work.reach, lenses=work.lenses),
            put,
        )
        if not isinstance(outcome, Answered):
            return Answer(text=None, refused=True)
        return Answer(
            text=outcome.text,
            minor=estimate(
                CostInputs(
                    lane=Lane.ANSWER,
                    tier=Tier.MAIN,
                    tool_calls=ESTIMATED_TOOL_CALLS,
                )
            ).minor,
            seconds=time.monotonic() - began,
        )

    return ask


@dataclass(frozen=True)
class Prepared:
    """A coordinating agent as one asker meets it now: the agent, who it may call and the lens."""

    record: AgentRecord
    #: The agents it may call that the asker may start, loaded as they are now.
    callees: dict[str, Callee]
    #: The same, as the planner is shown them.
    offered: list[Offered]
    lead: Coordinator


async def prepare(request: Request, asked: Asking, coordinator_id: str) -> Prepared:
    """The coordinator the asker may start, its callable agents and whether it may fan out.

    The one place a coordinating agent is assembled, so the route and an install check that drives
    the engine read it the same way. A coordinator the asker may not start is the one 404.
    """
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, coordinator_id, asked)
    callees, offered = await _callees_for(request, record, asked)
    lead = Coordinator(
        agent_id=record.agent_id,
        ceiling=entitlement_ceiling(record),
        callable_ids=frozenset(callees),
        may_fan_out=await coordination_of(request).fan_out(record.agent_id),
    )
    return Prepared(record=record, callees=callees, offered=offered, lead=lead)


async def _callees_for(
    request: Request, record: AgentRecord, asked: Asking
) -> tuple[dict[str, Callee], list[Offered]]:
    """The agents this coordinator may call that the asker may start, loaded as they are now."""
    allowed = await coordination_of(request).callees(record.agent_id)
    factory = _require_session_factory(request)
    loaded: dict[str, Callee] = {}
    offered: list[Offered] = []
    async with factory() as session:
        for callee_id in allowed:
            row = (await session.execute(one_agent(callee_id))).scalar_one_or_none()
            found = record_of(row) if row is not None else None
            if found is None or callee_id not in runnable_agent_ids((found,), viewer_of(asked)):
                continue
            loaded[callee_id] = Callee(
                agent_id=callee_id, tier=Tier(found.tier), ceiling=entitlement_ceiling(found)
            )
            offered.append(Offered(agent_id=callee_id, display_name=found.display_name))
    return loaded, offered


@router.post(RUNS_PATH, response_model=CoordinatedRunView, responses=_TOLD)
async def coordinate_request(
    request: Request, body: RunAsked, asked: Asked
) -> CoordinatedRunView | JSONResponse:
    """Split a request between a coordinating agent's specialists, run them, and merge the answer.

    See `NOTHING_RUNS_UNTIL_THE_PLAN_HAS_PASSED_EVERY_CHECK`. The asker is anybody who may start the
    coordinator, and everything runs at their own reach narrowed by both agents and each subtask.
    """
    if not await coordination_is_on(request):
        return _not_changed(REFUSED, NOT_SWITCHED_ON)
    prepared = await prepare(request, asked, body.coordinator_id)
    record, callees, offered = prepared.record, prepared.callees, prepared.offered
    if not offered:
        return _not_changed(REFUSED, NO_SPECIALISTS_HERE)
    try:
        request_text = checked_request(body.ask)
    except PlanRefusedError as refused:
        return _not_changed(REFUSED, refused.reasons[0])
    calls = planner_calls_of(request)
    if calls is None:
        return _not_changed(UNAVAILABLE, NO_MODEL_HERE)
    meter = Meter()
    try:
        reply = await calls.complete(
            planner_messages(request_text, offered),
            tier=PLANNER_TIER,
            lane=Lane.ANSWER,
            meter=meter,
            trace_id=_trace_id(),
            max_output_tokens=REPLY_TOKENS,
            categories=(DataCategory.QUESTION,),
        )
    except (ProviderUnavailable, NoCompliantRoute):
        await _spent(request, asked, meter, answered=False, completed_at=datetime.now(UTC))
        return _not_changed(UNAVAILABLE, NO_ANSWER_NOW)
    await _spent(request, asked, meter, answered=True, completed_at=datetime.now(UTC))
    try:
        steps = read_plan(reply.text, callees)
    except PlanRefusedError as refused:
        log.info("plan refused", reasons=len(refused.reasons), principal=asked.caller.principal.id)
        return _not_changed(REFUSED, THE_PLAN_COULD_NOT_BE_USED)
    run_id = f"coordinated-{uuid.uuid4().hex[:16]}"
    sessions = sessions_of(request)
    halts = await read_state(sessions) if sessions is not None else NOTHING_HALTED
    ran = await coordinate(
        run_id=run_id,
        coordinator=prepared.lead,
        steps=steps,
        callees=callees,
        caller=asked.reach,
        specialist=AskingSpecialist(_asking_the_specialist(request, asked, run_id)),
        rooms=LedgerRooms(request, now=asked.now, halts=halts),
        traffic=TrafficClass.HUMAN_INTERACTIVE
        if asked.channel is Channel.CONSOLE
        else TrafficClass.HUMAN_ASYNC,
        at=asked.now,
    )
    if ran.merged is None:
        log.info("coordinated run refused", principal=asked.caller.principal.id)
        return _not_changed(REFUSED, THE_PLAN_COULD_NOT_BE_USED)
    await _keep(request, ran, record.agent_id, asked)
    log.info(
        "coordinated run",
        run=run_id,
        mode=ran.mode.value if ran.mode else "",
        children=len(ran.children),
        principal=asked.caller.principal.id,
    )
    return _view(ran, {one.subtask_id for one in steps})


class RunKeeper(Protocol):
    """Keeps a started run and the gate's decision for it, in the asker's own name."""

    async def keep(
        self, ran: Coordinated, *, coordinator_id: str, at: datetime, by: str
    ) -> None: ...


class StoredRunKeeper:
    """`RunKeeper` over `ops.fanout_gate` and `ops.coordinated_run`, in one transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def keep(self, ran: Coordinated, *, coordinator_id: str, at: datetime, by: str) -> None:
        if ran.dispatch.gate is None:
            return
        async with self._sessions() as session, session.begin():
            await fanout_gate_store.keep(session, ran.dispatch.gate, by=by)
            await coordinated_run_store.keep(
                session, ran, coordinator_id=coordinator_id, at=at, by=by
            )


def keeper_of(request: Request) -> RunKeeper | None:
    """`app.state.coordinated_run_keeper` when something put one there, the database otherwise,
    or None on a process with no database, which has nowhere to keep a run."""
    found = getattr(request.app.state, "coordinated_run_keeper", None)
    if found is not None:
        return cast(RunKeeper, found)
    factory = sessions_of(request)
    return None if factory is None else StoredRunKeeper(factory)


async def _keep(request: Request, ran: Coordinated, coordinator_id: str, asked: Asking) -> None:
    """Keep the gate's decision and the run, in the asker's name, when there is somewhere to."""
    keeper = keeper_of(request)
    if keeper is not None:
        await keeper.keep(
            ran, coordinator_id=coordinator_id, at=asked.now, by=asked.caller.principal.id
        )


def _view(ran: Coordinated, ids: set[str]) -> CoordinatedRunView:
    assert ran.merged is not None and ran.mode is not None  # a started run has both
    gate = ran.dispatch.gate
    return CoordinatedRunView(
        run_id=ran.run_id,
        mode=ran.mode.value,
        why=[one.value for one in ran.why],
        gate=None if gate is None else gate_view(gate, None),
        children=[
            ChildView(
                subtask_id=one.subtask_id,
                callee_id=one.callee_id,
                depth=one.depth,
                status=one.status.value,
                seconds=one.seconds,
            )
            for one in ran.children
        ],
        merged=merged_view(ran.merged, frozenset(ids)),
    )


@router.get(RUNS_PATH, response_model=KeptRunsPage, responses=COMMON_RESPONSES)
async def coordinated_runs(request: Request, asked: Asked) -> KeptRunsPage:
    """The runs kept, newest first, for a caller who may weigh a plan.

    The authority is the one that reads the gate's decisions: how agents are used across the
    install is a question about the install and not about one agent.
    """
    if not may_rehearse(asked.reach, asked.now):
        log.info("coordinated runs not answerable", principal=asked.caller.principal.id)
        raise Absent("the coordination screen is not answerable for this caller")
    from brain.locale import currency_or_unset

    factory = _require_session_factory(request)
    async with factory() as session:
        kept = await coordinated_run_store.recent(session)
    currency = currency_or_unset()
    return KeptRunsPage(
        runs=[
            KeptRunView(
                run_id=one.run_id,
                coordinator_id=one.coordinator_id,
                started_at=one.started_at,
                asked_by=one.by,
                mode=one.mode.value,
                why=[why.value for why in one.why],
                children=[
                    KeptChildView(
                        subtask_id=child.subtask_id,
                        callee_id=child.callee_id,
                        depth=child.depth,
                        reach_hash=child.reach_hash,
                        status=child.status.value,
                        cost_minor=child.minor,
                        seconds=child.seconds,
                    )
                    for child in one.children
                ],
                complete=one.complete,
                total_minor=one.total_minor,
                currency=currency,
            )
            for one in kept
        ],
        switched_on=await coordination_is_on(request),
    )


# Kept so a reader of the route sees the one sentence an unusable plan is told, beside the others.
__all__ = ["NOTHING_WAS_STARTED", "router"]
