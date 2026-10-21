"""Stored workflows, over HTTP: write one, assign it to an agent, run it, and read what a run did.

`brain.orchestration.workflow` reads a definition and `brain.orchestration.workflow_run` runs one;
nothing could reach either. This is the door, and it adds no rule of its own about what a step may
touch: every step goes through the gate's own path for a tool call, at the asker's reach narrowed by
the agent it is run through.

**Writing a workflow is the authority over agents, held over everything.** A workflow is not one
agent's: it is assigned to agents, and saving one is a statement about how agents are used across
the install, as weighing a plan is. So it asks `admin:agent_lifecycle` over everything
(`brain.orchestration_routes.may_rehearse`), and a caller without it is answered as for a screen
that is not there. A definition the reader refuses is told to its author with every reason, because
the reasons are about what the author wrote. Saving writes the next version and edits nothing.

**Assigning is the lifecycle authority over the agent**, as allowing a callee is, and the one 404
for a hidden agent. An assignment says an agent may run a workflow and confers no reach.

**Running is anybody who may start the agent, behind a switch that ships off.** The order is fixed
and each step stops the rest: the switch, the agent (one the asker may start), the assignment, the
newest version, the steps. An agent not assigned the workflow and a workflow that does not exist are
**one sentence**, so a request cannot ask which workflows exist (M17.7.7), and the refusal comes
before the first step runs.

**The door is the gate's.** `GateDoor` hands each step to `brain.ops.automation_piece.call_piece`
with the asker's reach, the agent's ceiling and the agent's allowed tools, the projected catalogue,
the field policy and the redactor: a tool the asker cannot reach, a tool the agent may not call and
a tool that does not exist are one refusal, and the run goes on as the definition says. It runs with
an empty leash, under which a tool that changes something is not offered, so a step marked `writes`
is stated as not offered until a held action from an unattended run has been shown to reach the
right person. Nothing here computes a reach.

**A run ends with one trace, one signal and, for a repeated failure, one candidate**
(`brain.ops.workflow_store.finish`), in one transaction. The trace is statuses and words; the signal
is `automation.run_finished` for the entity `workflow_run`, naming the workflow, the agent and the
first step that failed; the candidate is a row for a person to decide and changes nothing.

Task ids: M17.6.1, M17.6.2, M17.6.7, M17.6.8, M17.7.7
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import _actionable, _not_changed, holds
from brain.agent_routes import _require_session_factory, _visible_record, viewer_of
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.agents.model import AgentRecord, entitlement_ceiling, runnable_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking, field_policies
from brain.automation_routes import RegistryToolCaller
from brain.core.errors import Absent, Failed
from brain.gate.finish import Origin, RequestRecorder
from brain.gate.injection import assess
from brain.gate.invoke import InvocationRefusedError
from brain.gate.leash import Leash
from brain.ops import workflow_store
from brain.ops.automation_piece import PieceRefusedError, PieceStep, call_piece
from brain.ops.features import is_on
from brain.ops.features_declared.stored_workflows import STORED_WORKFLOWS
from brain.orchestration.workflow import WorkflowError
from brain.orchestration.workflow_run import (
    RunRecord,
    StepCall,
    StepRefusedError,
    StepResult,
    run_workflow,
)
from brain.orchestration_routes import may_rehearse
from brain.routing_routes import sessions_of
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why an agent that was not assigned a workflow and a workflow that is not there are one answer.
AN_UNASSIGNED_WORKFLOW_AND_A_MISSING_ONE_ARE_ONE_REFUSAL: Final = (
    "A request to run a workflow through an agent is refused with one sentence when the agent was "
    "not assigned it and when there is no such workflow, so asking cannot tell which workflows "
    "exist. The refusal comes before the first step runs."
)

#: What the gate's own door is held to, said where a reader of a run will look.
A_WORKFLOW_STEP_IS_AN_AGENTS_OWN_CALL: Final = (
    "Each step goes through the gate as an agent's own tool call does: the asker's reach narrowed "
    "by the agent, the projected catalogue, the field policy and the redactor. A workflow has no "
    "way to reach what its agent could not."
)

NOT_SWITCHED_ON: Final = (
    "Nothing was started: running a stored workflow is not switched on for this company yet."
)
NOT_ASSIGNED: Final = "Nothing was started: that agent does not run that workflow."
NOT_SAVED: Final = "Nothing was saved: "
SAVED_FIRST: Final = "Nothing was saved: somebody saved this workflow just now. Open it again."
NOTHING_TO_WITHDRAW: Final = "Nothing was changed: that workflow was not assigned to this agent."
NO_WORKFLOW_TO_ASSIGN: Final = "Nothing was changed: there is no such workflow to assign."
REFUSED: Final = "refused"

# ------------------------------------------------------------------------ the figures
WORKFLOWS_PATH: Final = "/workflows"
WORKFLOW_PATH: Final = "/workflows/{workflow_id}"
ASSIGNED_PATH: Final = "/agents/{agent_id}/workflows"
UNASSIGNED_PATH: Final = "/agents/{agent_id}/workflows/removals"
RUN_PATH: Final = "/agents/{agent_id}/workflow-runs"
RUNS_PATH: Final = "/workflow-runs"

WORKFLOW_ID: Final = r"^[a-z][a-z0-9_-]{1,59}$"


# ------------------------------------------------------------------------------ the views
class WorkflowSaveAsked(BaseModel):
    """A workflow to save as its next version: its slug and the definition, read by the reader."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: Annotated[str, Field(pattern=WORKFLOW_ID)]
    definition: dict[str, Any]


class WorkflowIdAsked(BaseModel):
    """One workflow, by its slug."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+$")]


class WorkflowSavedView(BaseModel):
    """What saving a workflow came to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: str
    version: int
    name: str
    steps: int


class WorkflowListedView(BaseModel):
    """One workflow in the list: its newest version and name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: str
    version: int
    name: str


class WorkflowListView(BaseModel):
    """The workflows written, and whether running one is switched on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflows: list[WorkflowListedView]
    switched_on: bool


class WorkflowDefinitionView(BaseModel):
    """The newest saved version of a workflow, as it was saved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: str
    version: int
    saved_by: str
    saved_at: datetime
    definition: dict[str, Any]


class WorkflowAssignedView(BaseModel):
    """The workflows an agent may run, as this reader may be told them.

    Empty and `names_shown` false for a reader who does not answer for the agent, so the body is the
    same whether an agent has workflows or none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    names_shown: bool
    workflows: list[str] = []
    may_change: bool
    switched_on: bool


class WorkflowStepView(BaseModel):
    """What became of one step: a status and a word from a closed list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str
    status: str
    cause: str | None = None
    #: A skipped step's condition in the definition's own words.
    detail: str = ""
    attempts: int
    seconds: float


class WorkflowRunView(BaseModel):
    """One run: how it ended, the first step that failed and every step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    workflow_id: str
    version: int
    agent_id: str
    outcome: str
    failed_step: str | None
    steps: list[WorkflowStepView]
    #: The steps a candidate was opened for because they failed in each of the last runs.
    candidates_opened: list[str] = []


class WorkflowKeptRunView(WorkflowRunView):
    """A run that was kept, with who ran it and when."""

    run_by: str
    started_at: datetime


class WorkflowKeptRunsPage(BaseModel):
    """The runs kept, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: list[WorkflowKeptRunView]


# ------------------------------------------------------------------------------ the store
class Workflows(Protocol):
    """What these routes keep, in a form a test can hold in memory."""

    async def save(self, *, workflow_id: str, raw: Any, by: str) -> int: ...

    async def latest(self, workflow_id: str) -> workflow_store.Stored | None: ...

    async def listing(self) -> tuple[workflow_store.Listed, ...]: ...

    async def assigned(self, agent_id: str) -> tuple[str, ...]: ...

    async def assign(self, *, agent_id: str, workflow_id: str, by: str) -> bool: ...

    async def unassign(self, *, agent_id: str, workflow_id: str, by: str) -> bool: ...

    async def finish(
        self, record: RunRecord, *, at: datetime, by: str
    ) -> workflow_store.Finished: ...

    async def runs(self, workflow_id: str | None) -> tuple[workflow_store.KeptRun, ...]: ...


class StoredWorkflows:
    """`Workflows` over the four tables, each write in the caller's own name."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, *, workflow_id: str, raw: Any, by: str) -> int:
        async with self._sessions() as session, session.begin():
            return await workflow_store.save(session, workflow_id=workflow_id, raw=raw, by=by)

    async def latest(self, workflow_id: str) -> workflow_store.Stored | None:
        async with self._sessions() as session:
            return await workflow_store.latest(session, workflow_id)

    async def listing(self) -> tuple[workflow_store.Listed, ...]:
        async with self._sessions() as session:
            return await workflow_store.listing(session)

    async def assigned(self, agent_id: str) -> tuple[str, ...]:
        async with self._sessions() as session:
            return await workflow_store.assigned_to(session, agent_id)

    async def assign(self, *, agent_id: str, workflow_id: str, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await workflow_store.assign(
                session, agent_id=agent_id, workflow_id=workflow_id, by=by
            )

    async def unassign(self, *, agent_id: str, workflow_id: str, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await workflow_store.unassign(
                session, agent_id=agent_id, workflow_id=workflow_id, by=by
            )

    async def finish(self, record: RunRecord, *, at: datetime, by: str) -> workflow_store.Finished:
        async with self._sessions() as session, session.begin():
            return await workflow_store.finish(session, record, at=at, by=by)

    async def runs(self, workflow_id: str | None) -> tuple[workflow_store.KeptRun, ...]:
        async with self._sessions() as session:
            return await workflow_store.recent_runs(session, workflow_id=workflow_id)


def workflows_of(request: Request) -> Workflows:
    """`app.state.workflows` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "workflows", None)
    if found is not None:
        # A cast at the seam a test fills: whatever is put on `app.state` is held to this protocol
        # by the tests that put it there, and a runtime check would add nothing.
        return cast(Workflows, found)
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredWorkflows(factory)


async def workflows_are_on(request: Request) -> bool:
    """Whether a workflow may be run on this install. Off until somebody turns it on.

    `app.state.stored_workflows_on` wins when something put a boolean there, as every other switch
    read here does, so a test can say it without a database.
    """
    found = getattr(request.app.state, "stored_workflows_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, STORED_WORKFLOWS)


# ------------------------------------------------------------------------------ the door
class GateDoor:
    """`brain.orchestration.workflow_run.StepDoor` over the gate's path for a tool call.

    See `A_WORKFLOW_STEP_IS_AN_AGENTS_OWN_CALL`. Offers no writes: the leash is empty, under which
    only a tool that reads is offered.
    """

    writes_offered = False

    def __init__(self, request: Request, asked: Asking, record: AgentRecord) -> None:
        registry = getattr(request.app.state, "tools", None)
        if not isinstance(registry, ToolRegistry):
            # A process-level fault, identical for every caller and every question.
            raise Failed("no tool registry on this process")
        self._request = request
        self._asked = asked
        self._record = record
        self._registry = registry

    async def carry_out(self, call: StepCall) -> StepResult:
        asked, record = self._asked, self._record
        try:
            step = PieceStep(tool=call.target, arguments=dict(call.arguments))
        except ValidationError as refused:
            raise StepRefusedError from refused
        recorders: tuple[RequestRecorder, ...] = getattr(
            self._request.app.state, "request_recorders", ()
        )
        try:
            payload = await call_piece(
                step,
                origin=Origin(
                    trace_id=f"{call.run_id}-{call.step_id}",
                    principal=asked.caller.principal,
                    channel=asked.channel,
                ),
                recorders=recorders,
                flow_id=record.agent_id,
                caller=asked.reach,
                flow_ceiling=entitlement_ceiling(record),
                declared_tools=frozenset(record.authority.allowed_tools),
                registry=self._registry,
                leash=Leash(),
                assessment=assess(json.dumps(call.arguments, sort_keys=True, default=str)),
                policies=field_policies(self._registry),
                tools=RegistryToolCaller(self._registry, bound={"agent_id": record.agent_id}),
                now=asked.now,
                clock=lambda: datetime.now(UTC),
            )
        except (InvocationRefusedError, PieceRefusedError) as refused:
            raise StepRefusedError from refused
        return StepResult(records=tuple(payload.records))


# ------------------------------------------------------------------------------ the routes
router = APIRouter(prefix=API_PREFIX, tags=["orchestration"])

_TOLD: Final = {**COMMON_RESPONSES}


def _not_answerable() -> Absent:
    return Absent("the workflow screen is not answerable for this caller")


def _step_views(steps: Any) -> list[WorkflowStepView]:
    return [
        WorkflowStepView(
            step_id=one.step_id,
            status=getattr(one.status, "value", one.status),
            cause=getattr(one.cause, "value", one.cause),
            detail=one.detail,
            attempts=one.attempts,
            seconds=one.seconds,
        )
        for one in steps
    ]


@router.get(WORKFLOWS_PATH, response_model=WorkflowListView, responses=COMMON_RESPONSES)
async def list_workflows(request: Request, asked: Asked) -> WorkflowListView:
    """The workflows written, for a caller who may weigh how agents are used."""
    if not may_rehearse(asked.reach, asked.now):
        raise _not_answerable()
    listed = await workflows_of(request).listing()
    return WorkflowListView(
        workflows=[
            WorkflowListedView(workflow_id=one.workflow_id, version=one.version, name=one.name)
            for one in listed
        ],
        switched_on=await workflows_are_on(request),
    )


@router.post(WORKFLOWS_PATH, response_model=WorkflowSavedView, status_code=201, responses=_TOLD)
async def save_workflow(
    request: Request, body: WorkflowSaveAsked, asked: Asked
) -> WorkflowSavedView | JSONResponse:
    """Save a definition as the next version of a workflow, in the caller's name.

    A definition the reader refuses is told with every reason and writes nothing.
    """
    if not may_rehearse(asked.reach, asked.now):
        log.info("workflow not saved: refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    store = workflows_of(request)
    try:
        version = await store.save(
            workflow_id=body.workflow_id, raw=body.definition, by=asked.caller.principal.id
        )
    except WorkflowError as refused:
        return _not_changed(REFUSED, NOT_SAVED + "; ".join(refused.reasons[:6]) + ".")
    except workflow_store.SavedFirstError:
        return _not_changed(REFUSED, SAVED_FIRST)
    stored = await store.latest(body.workflow_id)
    assert stored is not None  # it was just written
    log.info("workflow saved", workflow=body.workflow_id, version=version)
    return WorkflowSavedView(
        workflow_id=body.workflow_id,
        version=version,
        name=stored.definition.name,
        steps=len(stored.definition.steps),
    )


@router.get(WORKFLOW_PATH, response_model=WorkflowDefinitionView, responses=COMMON_RESPONSES)
async def read_workflow(request: Request, workflow_id: str, asked: Asked) -> WorkflowDefinitionView:
    """The newest saved version of one workflow, as it was saved."""
    if not may_rehearse(asked.reach, asked.now):
        raise _not_answerable()
    stored = await workflows_of(request).latest(workflow_id)
    if stored is None:
        raise _not_answerable()
    return WorkflowDefinitionView(
        workflow_id=stored.workflow_id,
        version=stored.version,
        saved_by=stored.saved_by,
        saved_at=stored.saved_at,
        definition=_json_of(stored),
    )


def _json_of(stored: workflow_store.Stored) -> dict[str, Any]:
    from brain.orchestration.workflow import Ref

    def arg(value: object) -> object:
        return {"$ref": str(value)} if isinstance(value, Ref) else value

    steps: list[dict[str, Any]] = []
    for one in stored.definition.steps:
        step: dict[str, Any] = {
            "id": one.id,
            "kind": one.kind.value,
            "target": one.target,
            "arguments": {k: arg(v) for k, v in one.arguments.items()},
            "outputs": [
                {"name": o.name, "kind": o.kind.value, "path": o.path} for o in one.outputs
            ],
            "after": list(one.after),
            "parallel": one.parallel,
            "retry": {"limit": one.retry.limit, "backoff_seconds": one.retry.backoff_seconds},
            "on_failure": one.on_failure.value,
            "writes": one.writes,
        }
        if one.when is not None:
            step["when"] = {
                "ref": str(one.when.ref),
                "op": one.when.op.value,
                **({} if one.when.value is None else {"value": one.when.value}),
            }
        if one.handles is not None:
            step["handles"] = one.handles
        steps.append(step)
    return {"name": stored.definition.name, "steps": steps}


async def _assigned_view(
    request: Request, record: AgentRecord, asked: Asking
) -> WorkflowAssignedView:
    from brain.agent_audience_routes import answers_for

    answering = answers_for(record, asked)
    return WorkflowAssignedView(
        agent_id=record.agent_id,
        names_shown=answering,
        workflows=list(await workflows_of(request).assigned(record.agent_id)) if answering else [],
        may_change=holds(AGENT_LIFECYCLE_CAPABILITY, record, asked),
        switched_on=await workflows_are_on(request),
    )


@router.get(ASSIGNED_PATH, response_model=WorkflowAssignedView, responses=COMMON_RESPONSES)
async def agent_workflows(request: Request, agent_id: str, asked: Asked) -> WorkflowAssignedView:
    """The workflows one agent may run, told to those who answer for it."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    return await _assigned_view(request, record, asked)


@router.post(ASSIGNED_PATH, response_model=WorkflowAssignedView, responses=_TOLD)
async def assign_workflow(
    request: Request, agent_id: str, body: WorkflowIdAsked, asked: Asked
) -> WorkflowAssignedView | JSONResponse:
    """Let an agent run a workflow, in the caller's name. The workflow has to exist."""
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    store = workflows_of(request)
    if await store.latest(body.workflow_id) is None:
        return _not_changed(REFUSED, NO_WORKFLOW_TO_ASSIGN)
    await store.assign(
        agent_id=found.record.agent_id,
        workflow_id=body.workflow_id,
        by=asked.caller.principal.id,
    )
    log.info("workflow assigned", agent=found.record.agent_id, principal=asked.caller.principal.id)
    return await _assigned_view(request, found.record, asked)


@router.post(UNASSIGNED_PATH, response_model=WorkflowAssignedView, responses=_TOLD)
async def unassign_workflow(
    request: Request, agent_id: str, body: WorkflowIdAsked, asked: Asked
) -> WorkflowAssignedView | JSONResponse:
    """Withdraw an assignment, in the caller's name. The row stays."""
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    done = await workflows_of(request).unassign(
        agent_id=found.record.agent_id,
        workflow_id=body.workflow_id,
        by=asked.caller.principal.id,
    )
    if not done:
        return _not_changed(REFUSED, NOTHING_TO_WITHDRAW)
    return await _assigned_view(request, found.record, asked)


@router.post(RUN_PATH, response_model=WorkflowRunView, responses=_TOLD)
async def run_assigned_workflow(
    request: Request, agent_id: str, body: WorkflowIdAsked, asked: Asked
) -> WorkflowRunView | JSONResponse:
    """Run a workflow through an agent that was assigned it, as the person who asked.

    See the module docstring for the order. Each step goes through the gate at the asker's reach
    narrowed by the agent, and the run ends with one trace, one signal and, for a repeated failure,
    one candidate.
    """
    if not await workflows_are_on(request):
        return _not_changed(REFUSED, NOT_SWITCHED_ON)
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    if record.agent_id not in runnable_agent_ids((record,), viewer_of(asked)):
        raise _not_answerable()
    store = workflows_of(request)
    # One sentence for an agent not assigned the workflow and a workflow that is not there.
    if body.workflow_id not in await store.assigned(record.agent_id):
        return _not_changed(REFUSED, NOT_ASSIGNED)
    stored = await store.latest(body.workflow_id)
    if stored is None:
        return _not_changed(REFUSED, NOT_ASSIGNED)
    run_id = f"workflow-{uuid.uuid4().hex[:16]}"
    began = time.monotonic()
    ran = await run_workflow(
        run_id=run_id,
        workflow_id=stored.workflow_id,
        version=stored.version,
        agent_id=record.agent_id,
        definition=stored.definition,
        door=GateDoor(request, asked, record),
    )
    finished = await store.finish(ran, at=asked.now, by=asked.caller.principal.id)
    log.info(
        "workflow run",
        run=run_id,
        outcome=ran.outcome.value,
        seconds=round(time.monotonic() - began, 3),
        principal=asked.caller.principal.id,
    )
    return WorkflowRunView(
        run_id=run_id,
        workflow_id=ran.workflow_id,
        version=ran.version,
        agent_id=ran.agent_id,
        outcome=ran.outcome.value,
        failed_step=ran.failed_step,
        steps=_step_views(ran.steps),
        candidates_opened=list(finished.candidates),
    )


@router.get(RUNS_PATH, response_model=WorkflowKeptRunsPage, responses=COMMON_RESPONSES)
async def kept_workflow_runs(
    request: Request, asked: Asked, workflow_id: str | None = None
) -> WorkflowKeptRunsPage:
    """The runs kept, newest first, for a caller who may weigh how agents are used."""
    if not may_rehearse(asked.reach, asked.now):
        raise _not_answerable()
    kept = await workflows_of(request).runs(workflow_id)
    return WorkflowKeptRunsPage(
        runs=[
            WorkflowKeptRunView(
                run_id=one.run_id,
                workflow_id=one.workflow_id,
                version=one.version,
                agent_id=one.agent_id,
                outcome=one.outcome,
                failed_step=one.failed_step,
                steps=_step_views(one.steps),
                run_by=one.run_by,
                started_at=one.started_at,
            )
            for one in kept
        ]
    )
