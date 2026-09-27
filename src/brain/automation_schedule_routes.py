"""An agent's installed automations over HTTP: what each has done, and the two confirmed controls
that start and stop one.

`brain.console.agent_automations` decides who may see an automation and what its history shows,
and `brain.console.automation_schedule` decides who may start or stop one and what the confirmation
is over. This module orders the questions and writes through
`brain.ops.automation_run_store.StoredAutomationSchedules`, and adds no rule of its own.

**The order is `brain.automation_gallery_routes`', for its reasons.** The Automations tab's own read
first, from the reach alone, then the agent through the audience, so an agent a caller may not see
and one that does not exist are one 404. Only then are the automations read, and the listing is
`automations_for`, which has no value meaning every agent.

**An automation the caller may not see is the same 404 as one that does not exist**, on the
listing and on both controls, so trying a start on somebody else's automation id tells nobody it
exists.

**What a run found is shown only to whom it ran as.** A run's result was computed at that person's
reach narrowed by the agent, so a colleague holding the queue screen's grant sees that the run
happened, when, and how it ended, and not what it found. See
`A_RESULT_IS_SHOWN_ONLY_TO_WHOM_IT_RAN_AS`.

**Two refusals are 409s and write nothing**, as the gallery's are: a confirmation that no longer
matches what would change, and a change that lost a race with a run or another person, which is the
store finding the automation no longer has the next run that was shown.

Task ids: M39.6.1.4, M39.6.1.5, M39.6.2.2, M38.2.2.5
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_routes import viewer_of
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_gallery_routes import CONFIRMATION, agent_records_of
from brain.console.agent_automations import (
    SchedulerChange,
    automations_for,
    history,
    schedule_basis,
)
from brain.console.automation_gallery import may_open_gallery, template_by_id
from brain.console.automation_schedule import (
    NotConfirmedError,
    ScheduleShown,
    cannot_start_because,
    changed,
    may_start,
    may_stop,
    shown_start,
    shown_stop,
)
from brain.core.errors import Absent, Failed
from brain.ops.automation_run import PausedBecause, RunRecord
from brain.ops.automation_run_store import Listed, StoredAutomationSchedules
from brain.routing_routes import sessions_of
from brain.tables.automation_run import STARTED

log = structlog.get_logger()

#: The addresses, under `API_PREFIX`. The console's query file names the same three.
LIST_PATH: Final = "/agents/{agent_id}/automations"
START_PATH: Final = "/agents/{agent_id}/automations/{automation_id}/start"
STOP_PATH: Final = "/agents/{agent_id}/automations/{automation_id}/stop"

#: Why a result is shown to one person.
A_RESULT_IS_SHOWN_ONLY_TO_WHOM_IT_RAN_AS: Final = (
    "A run's result was computed at the reach of the person it ran as, narrowed by the agent. "
    "Anybody else who may see the automation is shown that the run happened, when and how it "
    "ended, and never what it found, because what it found is what that person may read."
)

#: What a refused confirmation says.
LOOK_AGAIN: Final = (
    "What you confirmed is not what would change now: the automation, its next run or its "
    "cadence has moved since you looked. Nothing was changed. Look again and confirm."
)

#: What a change that lost a race says.
IT_MOVED: Final = (
    "The automation changed while you were confirming, by a run or by somebody else, so nothing "
    "was changed. Look again."
)

#: What a paused automation that was never started says.
NEVER_STARTED: Final = "Installed and not started yet."

#: What each reason an automation has no next run says, in words for the Automations tab.
STOPPED_BECAUSE: Final = {
    PausedBecause.STOPPED.value: "Stopped by a person.",
    PausedBecause.FAILED_REPEATEDLY.value: (
        "Paused after its runs failed repeatedly. Nothing it does is happening until somebody "
        "starts it again."
    ),
    PausedBecause.OWNER_GONE.value: (
        "Paused because the person it runs as is no longer here. It runs as nobody else."
    ),
    PausedBecause.AGENT_UNAVAILABLE.value: "Paused because its agent is not enabled.",
    PausedBecause.TASK_UNBUILT.value: "Paused because this install cannot perform it.",
    PausedBecause.OWNER_LOST_REACH.value: (
        "Paused because the person it runs as, through this agent, can no longer read what it "
        "reads."
    ),
}

#: The words a 409 carries.
UNCONFIRMED: Final = "unconfirmed"
MOVED: Final = "moved"


# ------------------------------------------------------------------------ the shapes
class RunView(BaseModel):
    """One run: when, how it ended, and, for whom it ran as, what it found."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finished_at: datetime
    outcome: str
    reason: str | None = None
    #: The task's lines, for the person it ran as. Empty for anybody else and for a run that failed.
    result: list[str]


class AutomationView(BaseModel):
    """One of an agent's automations, and what this reader may do to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    name: str
    runs_as: str
    runs_as_name: str
    schedule: str
    next_run_at: datetime | None
    #: Why it has no next run, in words, or null while it runs.
    paused_because: str | None
    last_run: RunView | None
    #: Present when this reader may start it now, with the digest a start must carry.
    start_confirmation: str | None = None
    start_becomes: datetime | None = None
    #: Present when this reader may stop it now.
    stop_confirmation: str | None = None
    #: Why it cannot be started on this install, when that is why.
    cannot_start: str | None = None


class AutomationsView(BaseModel):
    """This agent's automations this reader may see. No count of the rest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AutomationView]
    result_rule: str = A_RESULT_IS_SHOWN_ONLY_TO_WHOM_IT_RAN_AS


class ChangeAsked(BaseModel):
    """The confirmation of what was shown. Nothing that could say who, or when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confirmation: str = Field(min_length=64, max_length=64, pattern=CONFIRMATION)


class NotChangedView(BaseModel):
    """Why nothing was changed, in a word and a sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str
    sentence: str


# ------------------------------------------------------------------------ the store
@runtime_checkable
class AutomationSchedules(Protocol):
    """What these routes need of an agent's automations. `StoredAutomationSchedules` is one."""

    async def listed(self, agent_id: str) -> tuple[Listed, ...]: ...

    async def change(
        self,
        change: SchedulerChange,
        *,
        reason: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> bool: ...


def schedules_of(request: Request) -> AutomationSchedules:
    """`app.state.automation_schedules` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "automation_schedules", None)
    if isinstance(found, AutomationSchedules):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAutomationSchedules(factory)


def _not_here(reason: str, asked: Asking) -> Absent:
    log.info("automation schedule refused", reason=reason, principal=asked.caller.principal.id)
    return Absent("no automation is answerable here for this caller")


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _visible(
    request: Request, agent_id: str, asked: Asking
) -> tuple[AgentRecord, tuple[Listed, ...]]:
    """The agent and its automations this reader may see, after the tab and the agent, or the
    404."""
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("tab", asked)
    record = await agent_records_of(request).agent(agent_id)
    if record is None or agent_id not in visible_agent_ids((record,), viewer_of(asked)):
        raise _not_here("agent", asked)
    every = await schedules_of(request).listed(agent_id)
    seen = {
        one.automation_id
        for one in automations_for(
            agent_id, [one.automation for one in every], asked.reach, asked.now
        )
    }
    return record, tuple(one for one in every if one.automation.automation_id in seen)


def run_view(run: RunRecord, asked: Asking) -> RunView:
    return RunView(
        finished_at=run.finished_at,
        outcome=run.outcome.value,
        reason=None if run.reason is None else run.reason.value,
        result=list(run.result) if run.principal_id == asked.caller.principal.id else [],
    )


def automation_view(listed: Listed, agent: AgentRecord, asked: Asking) -> AutomationView | None:
    """One automation as this reader sees it, or None when its template is gone."""
    one = listed.automation
    template = template_by_id(listed.template_id)
    if template is None:
        return None
    shown = history(
        one,
        [run.as_history() for run in listed.runs],
        asked.reach,
        basis=schedule_basis(asked.reach, asked.now),
        now=asked.now,
    )
    last = next(
        (run for run in listed.runs if shown.last is not None and run.finished_at == shown.last.at),
        None,
    )
    start = shown_start(one, template.cadence, now=asked.now)
    startable = start.becomes is not None and may_start(
        one, asked.reach, agent=agent, becomes=start.becomes, now=asked.now
    )
    stoppable = may_stop(one, asked.reach, now=asked.now)
    paused_because = None
    if one.paused:
        paused_because = (
            NEVER_STARTED
            if listed.stopped_because in (None, STARTED)
            else STOPPED_BECAUSE.get(listed.stopped_because or "", NEVER_STARTED)
        )
    return AutomationView(
        automation_id=one.automation_id,
        name=one.name,
        runs_as=one.runs_as.id,
        runs_as_name=one.runs_as.display_name,
        schedule=template.cadence.words(),
        next_run_at=one.next_run_at,
        paused_because=paused_because,
        last_run=None if last is None else run_view(last, asked),
        start_confirmation=start.confirmation if startable else None,
        start_becomes=start.becomes if startable else None,
        stop_confirmation=shown_stop(one, template.cadence).confirmation if stoppable else None,
        cannot_start=cannot_start_because(one, agent, asked.now) if one.paused else None,
    )


def _not_changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


router = APIRouter(prefix=API_PREFIX, tags=["automations"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
}


@router.get(LIST_PATH, response_model=AutomationsView, responses=COMMON_RESPONSES)
async def agent_automations(request: Request, agent_id: str, asked: Asked) -> AutomationsView:
    """This agent's automations this reader may see, each with its last run and its controls."""
    agent, seen = await _visible(request, agent_id, asked)
    views = (automation_view(one, agent, asked) for one in seen)
    return AutomationsView(items=[one for one in views if one is not None])


async def _change(
    request: Request,
    agent_id: str,
    automation_id: str,
    body: ChangeAsked,
    asked: Asking,
    *,
    starting: bool,
) -> JSONResponse:
    agent, seen = await _visible(request, agent_id, asked)
    listed = next((one for one in seen if one.automation.automation_id == automation_id), None)
    template = None if listed is None else template_by_id(listed.template_id)
    if listed is None or template is None:
        raise _not_here("automation", asked)
    one = listed.automation
    shown: ScheduleShown
    if starting:
        shown = shown_start(one, template.cadence, now=asked.now)
        if shown.becomes is None or not may_start(
            one, asked.reach, agent=agent, becomes=shown.becomes, now=asked.now
        ):
            raise _not_here("start", asked)
    else:
        if not may_stop(one, asked.reach, now=asked.now):
            raise _not_here("stop", asked)
        shown = shown_stop(one, template.cadence)
    try:
        change = changed(shown, confirmation=body.confirmation, guards=listed.guards)
    except NotConfirmedError:
        return _not_changed(UNCONFIRMED, LOOK_AGAIN)
    written = await schedules_of(request).change(
        change,
        reason=STARTED if starting else PausedBecause.STOPPED.value,
        actor=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
        at=asked.now,
    )
    if not written:
        return _not_changed(MOVED, IT_MOVED)
    after = change.after
    assert after is not None
    moved = Listed(
        automation=after,
        template_id=listed.template_id,
        guards=listed.guards,
        stopped_because=STARTED if starting else PausedBecause.STOPPED.value,
        runs=listed.runs,
    )
    view = automation_view(moved, agent, asked)
    return JSONResponse(
        status_code=200, content=None if view is None else view.model_dump(mode="json")
    )


@router.post(START_PATH, response_model=AutomationView, responses=_TOLD)
async def start_automation(
    request: Request, agent_id: str, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Start one paused automation at its cadence's next instant, confirmed, by somebody else."""
    return await _change(request, agent_id, automation_id, body, asked, starting=True)


@router.post(STOP_PATH, response_model=AutomationView, responses=_TOLD)
async def stop_automation(
    request: Request, agent_id: str, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Stop one running automation, confirmed, by whom it runs as or the authority over it."""
    return await _change(request, agent_id, automation_id, body, asked, starting=False)
