"""The Automations module over HTTP: every automation a reader may see, one automation's page and
figures, and the five confirmed changes the module makes.

`brain.console.automations` decides what an automation is now and who may change it,
`brain.console.agent_automations` who may see it, and `brain.ops.automation_run_store.
StoredAutomationSchedules` holds the SQL. This module orders the questions and adds no rule.

**Every list is still one agent at a time.** `agent_automations.automations_for` takes an agent id
with no value meaning every agent, and that stays true: the module's list is the union, over the
agents this reader may see through their audience, of each agent's own `automations_for`. So an
automation on an agent the reader cannot see is absent for the reason the agent is, and one the
reader may not see on an agent they can is absent for its own reason, and neither is counted.

**The order is `brain.automation_schedule_routes`', for its reasons.** The Automations read first,
from the reach alone; then the agent through its audience; then the automation through `may_see`.
An automation the reader may not see, one on an agent they may not see and one that does not exist
are one 404, on the page, the figures and every change.

**A change the reader may not make is the same 404**, so pressing Remove on somebody else's
automation id tells nobody it exists. Two refusals are 409s and write nothing: a confirmation that
no longer matches what the reader saw (`automations.shown`), and a change that lost a race with a
run or another person, which the store finds by folding the row again under its lock.

**What a run found is shown only to whom it ran as**, for `automation_schedule_routes.
A_RESULT_IS_SHOWN_ONLY_TO_WHOM_IT_RAN_AS`, and a reader shown only their own runs by
`agent_automations.schedule_basis` is shown figures over their own runs and told so.

**The figures are never cut off.** They are counted over the runs the page reads, and
`automation_run_store.RUNS_ON_ITS_PAGE` is more than the most frequent cadence, one run a day, can
make in the longest period the figures cover; `EVERY_RUN_IN_THE_LONGEST_PERIOD_IS_READ` says so and
a test holds the two against each other, so there is no "at least" to say.

**A run's cost is not recorded, and the figures say so rather than showing nought.** No automation
run writes `ops.spend_actual`: the one task this install performs reads a table and calls no model.
`RUN_COST_IS_NOT_RECORDED` is the reason the figures carry, for the shared stats routes' rule that a
figure nothing records is absent and never nought.

Task ids: M27.12.3, M27.15.37, M39.6.1.4, M39.6.1.5, M27.16.1
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Annotated, Final, Protocol, Self, runtime_checkable

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from brain.agent_routes import viewer_of
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_gallery_routes import agent_records_of
from brain.automation_schedule_routes import (
    IT_MOVED,
    LOOK_AGAIN,
    MOVED,
    STOPPED_BECAUSE,
    UNCONFIRMED,
    ChangeAsked,
    NotChangedView,
)
from brain.console.agent_automations import automations_for, history, schedule_basis
from brain.console.automation_gallery import WEEKDAYS, Cadence, Every, may_open_gallery
from brain.console.automation_schedule import cannot_start_because
from brain.console.automations import (
    Change,
    ChangeKind,
    State,
    may_adopt,
    may_pause,
    may_remove,
    may_reschedule,
    may_resume,
    rescheduled_next_run,
    shown,
    state_of,
)
from brain.console.workspace import Basis
from brain.core.errors import Absent, Failed
from brain.listing import Column, ListAsked, Listing
from brain.ops.automation_run import RUNNER_ACTOR, RunOutcome, RunRecord, next_run_after
from brain.ops.automation_run_store import (
    Detailed,
    Listed,
    StoredAutomationSchedules,
)
from brain.routing_routes import sessions_of
from brain.tables.automation_run import STARTED

log = structlog.get_logger()

#: The addresses, under `API_PREFIX`. The console's query file names the same ones.
LIST_PATH: Final = "/console/automations"
ONE_PATH: Final = "/console/automations/{automation_id}"
STATS_PATH: Final = "/console/automations/{automation_id}/stats"
PAUSE_PATH: Final = "/automations/{automation_id}/pause"
RESUME_PATH: Final = "/automations/{automation_id}/resume"
RESCHEDULE_PATH: Final = "/automations/{automation_id}/reschedule"
REMOVE_PATH: Final = "/automations/{automation_id}/remove"
ADOPT_PATH: Final = "/automations/{automation_id}/adopt"

#: Why the figures carry no cost.
RUN_COST_IS_NOT_RECORDED: Final = (
    "No automation run records a cost: the one outcome this install performs reads a table and "
    "calls no model, so there is nothing to meter yet."
)

#: What a person no longer in the directory is called on a page.
NO_LONGER_HERE: Final = "Someone no longer here"

#: What the runner is called in a history.
THE_RUNNER: Final = "The runner"

#: The periods the figures are given over, as the shared stats routes spell them.
PERIODS: Final[tuple[tuple[str, timedelta], ...]] = (
    ("7d", timedelta(days=7)),
    ("30d", timedelta(days=30)),
)

#: Why the figures are never an "at least".
EVERY_RUN_IN_THE_LONGEST_PERIOD_IS_READ: Final = (
    "The most frequent cadence runs once a day, so the longest period the figures cover holds at "
    "most one run a day and one more, and the page reads more runs than that, so every run in it "
    "is counted."
)

#: What a reschedule accepts, said before anybody submits one.
SCHEDULE_ACCEPTS: Final = (
    "Every day, every weekday or one day a week, at a whole hour in UTC (0 to 23)."
)

#: What each change does, in the words its confirmation shows.
CONFIRM_PAUSE: Final = "It stops running until somebody resumes it. Nothing it has done is undone."
CONFIRM_RESUME: Final = "It runs again at its next scheduled time, as the person it runs as."
CONFIRM_RESCHEDULE: Final = (
    "It will run on the new schedule. A paused automation stays paused until somebody resumes it."
)
CONFIRM_REMOVE: Final = (
    "It never runs again and cannot be resumed. Its runs and changes stay on this page."
)
CONFIRM_ADOPT: Final = (
    "It will run as you, at what you may reach through this agent. It stays paused until "
    "somebody else resumes it."
)

#: What a state reads as.
STATE_WORDS: Final[Mapping[State, str]] = {
    State.RUNNING: "Running",
    State.PAUSED: "Paused",
    State.OWNERLESS: "Ownerless",
    State.REMOVED: "Removed",
}

#: How a change reads in a history.
CHANGE_WORDS: Final[Mapping[ChangeKind, str]] = {
    ChangeKind.PAUSED: "Paused",
    ChangeKind.RESUMED: "Resumed",
    ChangeKind.RESCHEDULED: "Schedule changed to",
    ChangeKind.REMOVED: "Removed",
    ChangeKind.ADOPTED: "Adopted",
}

#: How a schedule row reads in a history, beside `STOPPED_BECAUSE` for its pauses.
STARTED_WORDS: Final = "Started"
INSTALLED_WORDS: Final = "Installed"

#: How the reach a run ran at compares with the run before it.
REACH_FIRST: Final = "first"
REACH_SAME: Final = "same"
REACH_CHANGED: Final = "changed"
REACH_NONE: Final = "none"


# ------------------------------------------------------------------------ the shapes
class AutomationRowView(BaseModel):
    """One automation on the module's list. Names, not ids, except the automation's own key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    name: str
    agent_id: str
    agent_name: str
    owner_name: str
    #: The cadence in words, or empty when nothing says when it runs.
    schedule: str
    state: State
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_outcome: str | None


class AutomationsPage(BaseModel):
    """One page of the automations this reader may see. Never a count of the rest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AutomationRowView]
    next_cursor: str | None = None


class CadenceView(BaseModel):
    """A cadence as its three fields, for a form's starting values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    every: Every
    hour_utc: int
    weekday: int | None = None


class AutomationRunView(BaseModel):
    """One run: when, how it ended, as whom, how its reach compares, and, for whom it ran as, what
    it found."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finished_at: datetime
    outcome: str
    #: Why it was refused, in words, or null.
    reason: str | None
    ran_as_name: str
    #: `first`, `same`, `changed` or `none` against the run before it.
    reach: str
    result: list[str]


class HistoryEntryView(BaseModel):
    """One thing that happened to the automation, newest first on the page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    what: str
    by_name: str


class AutomationDetailView(BaseModel):
    """One automation for its own page, and what this reader may do to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation: AutomationRowView
    #: What breaks if it does not run: the registry entry's sentence.
    guards: str
    #: Why it stopped, in words, while it has no next run.
    stopped_because: str | None
    #: Why it cannot be resumed on this install, when that is why.
    cannot_run: str | None
    cadence: CadenceView | None
    installed_by_name: str
    installed_at: datetime | None
    runs: list[AutomationRunView]
    #: Whose runs the list and the figures are over: `own` or `everyone`.
    basis: str
    history: list[HistoryEntryView]
    #: The digest every change must carry: this automation as it is shown here.
    confirmation: str
    may_pause: bool
    may_resume: bool
    resume_becomes: datetime | None
    may_reschedule: bool
    may_remove: bool
    may_adopt: bool
    schedule_accepts: str = SCHEDULE_ACCEPTS
    weekdays: list[str] = Field(default_factory=lambda: list(WEEKDAYS))
    confirm_pause: str = CONFIRM_PAUSE
    confirm_resume: str = CONFIRM_RESUME
    confirm_reschedule: str = CONFIRM_RESCHEDULE
    confirm_remove: str = CONFIRM_REMOVE
    confirm_adopt: str = CONFIRM_ADOPT
    #: Identifiers for the Advanced section.
    task: str
    template_id: str
    owner_id: str


class AutomationPeriodView(BaseModel):
    """One period's runs by how they ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    runs: int
    succeeded: int
    failed: int
    refused: int


class UnrecordedView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


class AutomationStatsView(BaseModel):
    """One automation's figures, over the runs this reader may be shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    basis: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    periods: list[AutomationPeriodView]
    unrecorded: list[UnrecordedView]


class RescheduleAsked(ChangeAsked):
    """The confirmation, and the new cadence. See `SCHEDULE_ACCEPTS`."""

    every: Every
    hour_utc: int = Field(ge=0, le=23)
    #: Monday is nought. Required for a weekly cadence and refused for any other.
    weekday: int | None = Field(default=None, ge=0, le=6)

    @model_validator(mode="after")
    def _a_day_exactly_when_weekly(self) -> Self:
        if (self.every is Every.WEEK) != (self.weekday is not None):
            msg = "a weekly schedule names its day, and no other schedule names one"
            raise ValueError(msg)
        return self

    def cadence(self) -> Cadence:
        return Cadence(every=self.every, hour_utc=self.hour_utc, weekday=self.weekday)


# ------------------------------------------------------------------------ the store
@runtime_checkable
class AutomationDirectory(Protocol):
    """What these routes need. `StoredAutomationSchedules` is one."""

    async def every(self) -> tuple[Listed, ...]: ...

    async def one(self, automation_id: str) -> Detailed | None: ...

    async def apply(
        self,
        automation_id: str,
        change: Change,
        *,
        expect: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...


def directory_of(request: Request) -> AutomationDirectory:
    """`app.state.automation_directory` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "automation_directory", None)
    if isinstance(found, AutomationDirectory):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAutomationSchedules(factory)


def _not_here(reason: str, asked: Asking) -> Absent:
    log.info("automation refused", reason=reason, principal=asked.caller.principal.id)
    return Absent("no automation is answerable here for this caller")


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _agents(request: Request, agent_ids: Iterable[str]) -> dict[str, AgentRecord]:
    records = agent_records_of(request)
    found: dict[str, AgentRecord] = {}
    for agent_id in sorted(set(agent_ids)):
        record = await records.agent(agent_id)
        if record is not None:
            found[agent_id] = record
    return found


async def _visible(
    request: Request, every: Sequence[Listed], asked: Asking
) -> list[tuple[Listed, AgentRecord]]:
    """The automations this reader may see, each with its agent: one agent at a time."""
    agents = await _agents(request, (one.automation.agent_id for one in every))
    kept: list[tuple[Listed, AgentRecord]] = []
    for agent_id in sorted(visible_agent_ids(agents.values(), viewer_of(asked))):
        mine = [one for one in every if one.automation.agent_id == agent_id]
        seen = {
            one.automation_id
            for one in automations_for(
                agent_id, [one.automation for one in mine], asked.reach, asked.now
            )
        }
        kept.extend((one, agents[agent_id]) for one in mine if one.automation.automation_id in seen)
    return kept


def _permitted(asked: Asking) -> None:
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("module", asked)


async def _one_visible(
    request: Request, automation_id: str, asked: Asking
) -> tuple[Detailed, AgentRecord]:
    """One automation this reader may see, whole, with its agent, or the one 404."""
    _permitted(asked)
    detailed = await directory_of(request).one(automation_id)
    if detailed is None:
        raise _not_here("automation", asked)
    seen = await _visible(request, (detailed.listed,), asked)
    if not seen:
        raise _not_here("automation", asked)
    return detailed, seen[0][1]


# ------------------------------------------------------------------------ the views
def _state(listed: Listed, now: datetime) -> State:
    return state_of(listed.automation, removed=listed.removed, owner_live=listed.owner_live(now))


def _visible_runs(listed: Listed, asked: Asking) -> tuple[Basis, list[RunRecord]]:
    """The runs this reader may be shown, newest first, at their basis."""
    basis = schedule_basis(asked.reach, asked.now)
    shown_runs = history(
        listed.automation,
        [run.as_history() for run in listed.runs],
        asked.reach,
        basis=basis,
        now=asked.now,
    )
    keep = {(one.at, one.principal_id) for one in shown_runs.runs}
    return basis, [run for run in listed.runs if (run.finished_at, run.principal_id) in keep]


def _owner_name(listed: Listed) -> str:
    return listed.owner_name or NO_LONGER_HERE


def row_view(listed: Listed, agent: AgentRecord, asked: Asking) -> AutomationRowView:
    one = listed.automation
    _, runs = _visible_runs(listed, asked)
    last = runs[0] if runs else None
    return AutomationRowView(
        automation_id=one.automation_id,
        name=one.name,
        agent_id=one.agent_id,
        agent_name=agent.display_name,
        owner_name=_owner_name(listed),
        schedule="" if listed.cadence is None else listed.cadence.words(),
        state=_state(listed, asked.now),
        next_run_at=one.next_run_at,
        last_run_at=None if last is None else last.finished_at,
        last_outcome=None if last is None else last.outcome.value,
    )


def _name(person: str, names: Mapping[str, str]) -> str:
    if person == RUNNER_ACTOR:
        return THE_RUNNER
    return names.get(person, NO_LONGER_HERE)


def _stopped_words(listed: Listed) -> str | None:
    if not listed.automation.paused:
        return None
    reason = listed.stopped_because
    if reason in (None, STARTED):
        return "Installed and not started yet."
    return STOPPED_BECAUSE.get(reason or "")


def _reach_words(runs: Sequence[RunRecord]) -> list[str]:
    """For each run, newest first, how its reach compares with the run before it that had one."""
    said: list[str] = []
    for index, run in enumerate(runs):
        if run.ent_hash is None:
            said.append(REACH_NONE)
            continue
        before = next((one for one in runs[index + 1 :] if one.ent_hash is not None), None)
        if before is None:
            said.append(REACH_FIRST)
        elif before.ent_hash == run.ent_hash and before.principal_id == run.principal_id:
            said.append(REACH_SAME)
        else:
            said.append(REACH_CHANGED)
    return said


def _history(detailed: Detailed) -> list[HistoryEntryView]:
    listed, names = detailed.listed, detailed.names
    entries: list[HistoryEntryView] = []
    if listed.installed_at is not None:
        entries.append(
            HistoryEntryView(
                at=listed.installed_at,
                what=INSTALLED_WORDS,
                by_name=_name(listed.installed_by, names),
            )
        )
    for row in detailed.schedule:
        what = (
            STARTED_WORDS if row.reason == STARTED else STOPPED_BECAUSE.get(row.reason, row.reason)
        )
        entries.append(HistoryEntryView(at=row.at, what=what, by_name=_name(row.changed_by, names)))
    for change in listed.changes:
        what = CHANGE_WORDS[change.kind]
        if change.cadence is not None:
            what = f"{what} {change.cadence.words()}"
        entries.append(
            HistoryEntryView(at=change.at, what=what, by_name=_name(change.changed_by, names))
        )
    return sorted(entries, key=lambda one: one.at, reverse=True)


def detail_view(detailed: Detailed, agent: AgentRecord, asked: Asking) -> AutomationDetailView:
    listed = detailed.listed
    one = listed.automation
    cadence = listed.cadence
    live = listed.owner_live(asked.now)
    basis, runs = _visible_runs(listed, asked)
    reach = _reach_words(runs)
    resumable = may_resume(
        one,
        asked.reach,
        agent=agent,
        cadence=cadence,
        removed=listed.removed,
        owner_live=live,
        now=asked.now,
    )
    cannot_run = None
    if one.paused and not listed.removed:
        cannot_run = cannot_start_because(one, agent, asked.now)
    return AutomationDetailView(
        automation=row_view(listed, agent, asked),
        guards=listed.guards,
        stopped_because=_stopped_words(listed),
        cannot_run=cannot_run,
        cadence=(
            None
            if cadence is None
            else CadenceView(
                every=cadence.every, hour_utc=cadence.hour_utc, weekday=cadence.weekday
            )
        ),
        installed_by_name=_name(listed.installed_by, detailed.names),
        installed_at=listed.installed_at,
        runs=[
            AutomationRunView(
                finished_at=run.finished_at,
                outcome=run.outcome.value,
                reason=None if run.reason is None else STOPPED_BECAUSE.get(run.reason.value),
                ran_as_name=_name(run.principal_id, detailed.names),
                reach=said,
                result=list(run.result) if run.principal_id == asked.caller.principal.id else [],
            )
            for run, said in zip(runs, reach, strict=True)
        ],
        basis=basis.value,
        history=_history(detailed),
        confirmation=shown(one, cadence=cadence, removed=listed.removed),
        may_pause=may_pause(one, asked.reach, removed=listed.removed, now=asked.now),
        may_resume=resumable,
        resume_becomes=(
            next_run_after(cadence, asked.now) if resumable and cadence is not None else None
        ),
        may_reschedule=cadence is not None
        and may_reschedule(
            one, asked.reach, becomes=cadence, removed=listed.removed, now=asked.now
        ),
        may_remove=may_remove(one, asked.reach, removed=listed.removed, now=asked.now),
        may_adopt=may_adopt(
            one, asked.reach, removed=listed.removed, owner_live=live, now=asked.now
        ),
        task=one.task,
        template_id=listed.template_id,
        owner_id=one.runs_as.id,
    )


def stats_view(listed: Listed, asked: Asking) -> AutomationStatsView:
    basis, runs = _visible_runs(listed, asked)
    periods = []
    for label, span in PERIODS:
        inside = [run for run in runs if run.finished_at > asked.now - span]
        outcomes = [run.outcome for run in inside]
        periods.append(
            AutomationPeriodView(
                range=label,
                runs=len(inside),
                succeeded=outcomes.count(RunOutcome.SUCCEEDED),
                failed=outcomes.count(RunOutcome.FAILED),
                refused=outcomes.count(RunOutcome.REFUSED),
            )
        )
    return AutomationStatsView(
        automation_id=listed.automation.automation_id,
        basis=basis.value,
        last_run_at=runs[0].finished_at if runs else None,
        next_run_at=listed.automation.next_run_at,
        periods=periods,
        unrecorded=[UnrecordedView(figure="run_cost", why=RUN_COST_IS_NOT_RECORDED)],
    )


# ------------------------------------------------------------------------ the routes
router = APIRouter(prefix=API_PREFIX, tags=["automations"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
}

AUTOMATIONS: Final[Listing[AutomationRowView]] = Listing(
    name="automations",
    columns=(
        Column("name", lambda row: row.name, search=True, sort=True),
        Column("agent", lambda row: row.agent_name, search=True, filter=True, sort=True),
        Column("owner", lambda row: row.owner_name, search=True, filter=True, sort=True),
        Column("state", lambda row: row.state.value, filter=True, sort=True),
        Column("schedule", lambda row: row.schedule, search=True),
        Column("next_run_at", lambda row: row.next_run_at, sort=True),
        Column("last_run_at", lambda row: row.last_run_at, sort=True),
    ),
    key=lambda row: row.automation_id,
    order="name",
)
AutomationsQuery = Annotated[ListAsked, Depends(AUTOMATIONS.query())]


@router.get(LIST_PATH, response_model=AutomationsPage, responses=COMMON_RESPONSES)
async def automations(request: Request, asked: Asked, listed: AutomationsQuery) -> AutomationsPage:
    """Every automation this reader may see, across the agents they may see (M27.12.3)."""
    _permitted(asked)
    plan = AUTOMATIONS.plan(listed, reader=asked.caller.principal.id)
    every = await directory_of(request).every()
    rows = [row_view(one, agent, asked) for one, agent in await _visible(request, every, asked)]
    page = plan.page(rows)
    return AutomationsPage(items=list(page.items), next_cursor=page.next_cursor)


@router.get(ONE_PATH, response_model=AutomationDetailView, responses=COMMON_RESPONSES)
async def automation(request: Request, automation_id: str, asked: Asked) -> AutomationDetailView:
    """One automation whole: its definition, schedule, runs, history and the changes offered."""
    detailed, agent = await _one_visible(request, automation_id, asked)
    return detail_view(detailed, agent, asked)


@router.get(STATS_PATH, response_model=AutomationStatsView, responses=COMMON_RESPONSES)
async def automation_stats(
    request: Request, automation_id: str, asked: Asked
) -> AutomationStatsView:
    """One automation's runs by outcome over seven and thirty days, over the runs this reader may
    be shown."""
    detailed, _ = await _one_visible(request, automation_id, asked)
    return stats_view(detailed.listed, asked)


def _not_changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _decided(
    kind: ChangeKind,
    detailed: Detailed,
    agent: AgentRecord,
    asked: Asking,
    becomes: Cadence | None,
) -> Change | None:
    """The change this reader may make, or None when they may not make it."""
    listed = detailed.listed
    one = listed.automation
    removed, live, now = listed.removed, listed.owner_live(asked.now), asked.now
    by = asked.caller.principal.id
    match kind:
        case ChangeKind.PAUSED:
            if not may_pause(one, asked.reach, removed=removed, now=now):
                return None
            return Change(kind=kind, at=now, changed_by=by)
        case ChangeKind.RESUMED:
            cadence = listed.cadence
            if cadence is None or not may_resume(
                one,
                asked.reach,
                agent=agent,
                cadence=cadence,
                removed=removed,
                owner_live=live,
                now=now,
            ):
                return None
            return Change(
                kind=kind, at=now, changed_by=by, next_run_at=next_run_after(cadence, now)
            )
        case ChangeKind.RESCHEDULED:
            if becomes is None or not may_reschedule(
                one, asked.reach, becomes=becomes, removed=removed, now=now
            ):
                return None
            return Change(
                kind=kind,
                at=now,
                changed_by=by,
                cadence=becomes,
                next_run_at=rescheduled_next_run(one, becomes=becomes, now=now),
            )
        case ChangeKind.REMOVED:
            if not may_remove(one, asked.reach, removed=removed, now=now):
                return None
            return Change(kind=kind, at=now, changed_by=by)
        case ChangeKind.ADOPTED:
            if not may_adopt(one, asked.reach, removed=removed, owner_live=live, now=now):
                return None
            return Change(kind=kind, at=now, changed_by=by, runs_as_id=by)


async def _change(
    request: Request,
    automation_id: str,
    confirmation: str,
    asked: Asking,
    kind: ChangeKind,
    becomes: Cadence | None = None,
) -> JSONResponse:
    detailed, agent = await _one_visible(request, automation_id, asked)
    change = _decided(kind, detailed, agent, asked, becomes)
    if change is None:
        raise _not_here(kind.value, asked)
    listed = detailed.listed
    expect = shown(listed.automation, cadence=listed.cadence, removed=listed.removed)
    if confirmation != expect:
        return _not_changed(UNCONFIRMED, LOOK_AGAIN)
    written = await directory_of(request).apply(
        automation_id,
        change,
        expect=expect,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        return _not_changed(MOVED, IT_MOVED)
    log.info("automation changed", change=kind.value, principal=asked.caller.principal.id)
    again, agent = await _one_visible(request, automation_id, asked)
    return JSONResponse(
        status_code=200, content=detail_view(again, agent, asked).model_dump(mode="json")
    )


@router.post(PAUSE_PATH, response_model=AutomationDetailView, responses=_TOLD)
async def pause_automation(
    request: Request, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Pause a running automation: whom it runs as, or the authority over it."""
    return await _change(request, automation_id, body.confirmation, asked, ChangeKind.PAUSED)


@router.post(RESUME_PATH, response_model=AutomationDetailView, responses=_TOLD)
async def resume_automation(
    request: Request, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Resume a paused automation with an owner, by the authority held by somebody else."""
    return await _change(request, automation_id, body.confirmation, asked, ChangeKind.RESUMED)


@router.post(RESCHEDULE_PATH, response_model=AutomationDetailView, responses=_TOLD)
async def reschedule_automation(
    request: Request, automation_id: str, body: RescheduleAsked, asked: Asked
) -> JSONResponse:
    """Change when an automation runs, by the authority held by somebody it does not run as."""
    return await _change(
        request, automation_id, body.confirmation, asked, ChangeKind.RESCHEDULED, body.cadence()
    )


@router.post(REMOVE_PATH, response_model=AutomationDetailView, responses=_TOLD)
async def remove_automation(
    request: Request, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Remove an automation for good, keeping its runs and changes."""
    return await _change(request, automation_id, body.confirmation, asked, ChangeKind.REMOVED)


@router.post(ADOPT_PATH, response_model=AutomationDetailView, responses=_TOLD)
async def adopt_automation(
    request: Request, automation_id: str, body: ChangeAsked, asked: Asked
) -> JSONResponse:
    """Adopt an ownerless automation in your own name. It stays paused (M27.15.37)."""
    return await _change(request, automation_id, body.confirmation, asked, ChangeKind.ADOPTED)
