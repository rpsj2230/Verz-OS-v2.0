"""The peak load runs this install has kept, beside the service levels they are judged against.

`brain.ops.load_run_store` keeps one row for each run of `python -m brain.ops.load_peak`: what it
drove, each lane's 95th percentile and success rate, and whether the service levels held. The row
was written for "the install's own checks and any later screen" to read, and no screen read it, so
the one test of the objectives the product says it holds was visible only to someone with a
database prompt. This is the read. It is the Service levels screen's, and it decides nothing the
store and `brain.ops.reliability` do not.

**Each lane's figures sit beside the objective that lane promises.** A run's p95 of three seconds
means nothing until it is read against the lane's eight; `reliability.lane_objective` is asked for
each lane the run measured, and a lane with no declared objective is shown with none rather than
dropped, so a lane added to a run and not to the objectives shows as unjudged.

**It is the service-level screen's reader, answered as that screen answers.** A run is a statement
about the whole install, as a reading is, so `service_level_view.may_read_service_levels` decides,
and a reader it refuses is answered with the list an install that has never been run produces: no
runs. A refusal that said "withheld" would tell a department head the install had been load tested.
See `A_REFUSED_READER_IS_SHOWN_AN_INSTALL_THAT_HAS_NEVER_BEEN_RUN`.

**A run smaller than the stated peak says so.** `at_stated_peak` is on every run, because a bounded
run that held is evidence the machinery works and not that the peak is carried. A record names no
person, token or question (`load_run_store.A_RECORD_NAMES_NO_ONE_AND_NO_QUESTION`), and neither
does this.

Task ids: M36.2.4.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.service_level_view import may_read_service_levels
from brain.core.errors import Failed
from brain.core.lane import Lane
from brain.ops.load_run_store import RunRecord, read_runs
from brain.ops.reliability import ReliabilityError, lane_objective
from brain.routing_routes import sessions_of

#: Why a reader the screen refuses is shown no runs rather than a refusal.
A_REFUSED_READER_IS_SHOWN_AN_INSTALL_THAT_HAS_NEVER_BEEN_RUN: Final = (
    "The service levels screen answers a reader it refuses with the reading of an install that "
    "promises nothing, so that a refusal and an empty answer are one object. The runs are answered "
    "the same way: a refusal that said so would tell a department head that the install had been "
    "load tested, and when."
)

#: How many runs one reading lists, newest first. A resource bound; the history is the rows.
RUNS_SHOWN: Final = 20


class LoadLaneView(BaseModel):
    """One lane's figures over a run, and the objective the lane is held to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane: str
    requests: int
    p95_ms: float | None
    success_rate: float | None
    shed: int
    #: The lane's declared 95th percentile in milliseconds, or None where it declares none.
    objective_p95_ms: float | None
    #: The lane's declared success rate, or None where the lane is declared no objective at all.
    objective_success_rate: float | None


class LoadRunView(BaseModel):
    """One peak run, as it was kept. No person, no token and no question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: datetime
    commit: str
    profile: str
    seconds_run: float
    planned: int
    sent: int
    not_sent: int
    most_in_flight: int
    at_stated_peak: bool
    held: bool
    interactive_shed: int
    lanes: list[LoadLaneView]
    findings: list[str]


class LoadRunsView(BaseModel):
    """The runs this install has kept, newest first, or none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: list[LoadRunView]


def view_of(record: RunRecord) -> LoadRunView:
    """One kept run, each lane beside its objective."""
    lanes: list[LoadLaneView] = []
    for one in record.lanes:
        try:
            objective = lane_objective(Lane(one.lane))
        except (ReliabilityError, ValueError):
            objective = None
        lanes.append(
            LoadLaneView(
                lane=one.lane,
                requests=one.requests,
                p95_ms=one.p95_ms,
                success_rate=one.success_rate,
                shed=one.shed,
                objective_p95_ms=None if objective is None else objective.p95_ms,
                objective_success_rate=None if objective is None else objective.success_rate,
            )
        )
    return LoadRunView(
        run_id=record.run_id,
        started_at=record.started_at,
        commit=record.commit,
        profile=record.profile,
        seconds_run=record.seconds_run,
        planned=record.planned,
        sent=record.sent,
        not_sent=record.not_sent,
        most_in_flight=record.most_in_flight,
        at_stated_peak=record.at_stated_peak,
        held=record.held,
        interactive_shed=record.interactive_shed,
        lanes=lanes,
        findings=list(record.findings),
    )


router = APIRouter(prefix=API_PREFIX, tags=["report"])


@router.get(
    "/report/service-levels/load-runs", response_model=LoadRunsView, responses=COMMON_RESPONSES
)
async def load_runs(request: Request, asked: Asked) -> LoadRunsView:
    """The peak runs kept on this install, newest first, for a reader of the service levels.

    See `A_REFUSED_READER_IS_SHOWN_AN_INSTALL_THAT_HAS_NEVER_BEEN_RUN`.
    """
    if not may_read_service_levels(asked.reach, now=asked.now):
        return LoadRunsView(runs=[])
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        kept = await read_runs(session)
    return LoadRunsView(runs=[view_of(one) for one in kept[:RUNS_SHOWN]])
