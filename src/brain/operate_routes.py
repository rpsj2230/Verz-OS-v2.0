"""The two Operate screens nobody could open: live runs, and models and health.

`docs/screens.html` SCREEN 1 draws the Operate section as Overview, Live runs, Models and health
and Connectors, and SCREEN 11 draws the Models screen itself. `brain.console.operate` declares
the runs and queue screens and decides who may see a run, `brain.console.screens` registers the
models screen, and until this module no route served either, so `brain.ops.console_screens`
printed both on every run. This is the read those decisions sit behind, and most of what is
argued below is what it refuses to answer, because most of what the design draws has no source
in an install today.

**What is running is the scheduled controls, because that is the only running work anything
records.** `brain.ops.jobs.JobRecord` is the shape of a job and no table holds one; the queue
driver's own tables are refused to the application role on purpose (see
`THE_QUEUE_IS_NOT_THE_APPLICATIONS_TO_READ`); and a question being answered leaves its row in
`obs.request_telemetry` when it finishes and not before. `ops.model_attempt` has held a model call
in flight since 2026-09-17 (`brain.models.calls`), and this screen does not read it yet.
`ops.control_run` is written when a control
starts and finished when it returns, so its newest unfinished row per control is exactly a run in
progress or a process that died holding one. That is what the screen shows, and the three things
it cannot show are fields on the response rather than empty tables. See
`A_SCREEN_OF_RUNS_SHOWS_THE_RUNS_SOMETHING_RECORDS_AND_SAYS_WHICH_ONES_NOTHING_DOES`.

**There is no stop control, because there is no safe path for one to reach.** A control holds a
transaction-scoped advisory lock inside a worker process for its whole run, and nothing in this
repository ends one: `brain.ops.jobs` has a cancelling state and nothing persists the row it
would move, the queue driver's cancellation is not called anywhere and its table cannot be read
from here, and `brain.ops.halt` stops admission rather than a run and has no route. A button
reaching none of those would be the control `docs/admin-console.md` calls worse than no control.
See `NO_RUN_CAN_BE_STOPPED_FROM_HERE`.

**Live runs has no capability check in front of it and models has one, and the difference is the
attribution.** A run is a per-person figure in `brain.console.operate.PANELS`: a reader without
the screen's grant is shown their own work, which today is nothing, so the runs route reads and
narrows for everybody, which is `brain.report_routes`' construction and its argument. The models
screen is whole-install: every figure on it is everybody's traffic and there is no narrower
version, so `brain.console.operate.figure_basis` either admits the reader to all of it or the
route refuses before it reads, which is `brain.routing_routes`' order and its argument.

**The models screen serves what only the API knows and nothing another route already serves.**
The chain is `GET /routing/rungs`, behind its own grant and editable there; the p95 against its
objective is `GET /report/service-levels`; the cost is `GET /report/spend`. Serving any of those
again here would be a second door to one set of rows under a different grant, and the two grants
would drift. What is here is the share of requests the fast lane answered without a model, the
providers this system holds a key slot for, what each tier is for, and the measurements that do
not exist, each in the sentence `brain.ops.telemetry.UNFILLABLE_TODAY` already wrote for it. See
`A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE`.

**Provider health, keys and switches are `brain.provider_routes`', and not this route's.** Until
2026-09-17 this response carried two flags saying no breaker was recorded and no key status was
served, because nothing called a model and `brain.console.model_matrix` would have drawn a closed
breaker nobody had tested. The executor calls models now, its attempts are the evidence, and
`GET /models/providers` serves each rung's measured health and whether each provider's key is
held, behind this screen's own basis. Serving either here as well would be one fact behind two
routes. What this route adds for the models screen is `fallbacks_fired`, the ledger's own sum over
the window.

**Not claimed: M27.8.13.** No run can be stopped, and a leaf closed over a screen that cannot
would be the tracker counting a read as a control.

**What has never run.** This repository has no PostgreSQL, so neither statement below has been
executed. What is tested is the SQL each compiles to, every decision over rows built in memory,
and the order the checks happen in.

Task ids: M27.2.2, M27.2.3, M27.2.6
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.operate import (
    ControlRun,
    OwedControl,
    figure_basis,
    panel,
    unattended_running,
    unattended_waiting,
)
from brain.console.workspace import Basis
from brain.core.errors import Absent, Failed
from brain.core.lane import Lane
from brain.models.routing import Tier
from brain.ops.controls import CONTROLS, Control
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.ops.schedule_runner import STALLED_AFTER, due_now, stalled_runs
from brain.ops.schedule_store import last_successes
from brain.ops.telemetry import UNFILLABLE_TODAY
from brain.report_routes import MAX_READING_HOURS
from brain.tables.schedule import ControlRunRow
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why the live runs screen shows controls and names the runs it cannot show.
A_SCREEN_OF_RUNS_SHOWS_THE_RUNS_SOMETHING_RECORDS_AND_SAYS_WHICH_ONES_NOTHING_DOES: Final = (
    "A live runs screen reads as the whole of what is happening. ops.control_run is the one "
    "table written when work starts, so its unfinished rows are real runs. A question being "
    "answered is recorded when it finishes, a model call in flight is recorded by nothing, and "
    "a queued job sits in a table the application may not read. An empty table beside those "
    "absences would say the install is idle while a person waits for an answer, so the response "
    "carries each absence as a field and the page says it in words."
)

#: Why the queue driver's rows are not read here.
THE_QUEUE_IS_NOT_THE_APPLICATIONS_TO_READ: Final = (
    "brain.ops.queue.driver_rls_statements enables row-level security on the driver's tables and "
    "creates no policy, which denies every row to brain_app and leaves the driver's own role "
    "working. That is deliberate: a queue table is a copy of work with no row-level security of "
    "its own and a different retention, and the application enqueues through the driver rather "
    "than selecting from it. A console reading the queue would need that decision reversed, and "
    "a policy of USING (true) would read as thoroughness and grant everything back."
)

#: Why there is no control that stops a run.
NO_RUN_CAN_BE_STOPPED_FROM_HERE: Final = (
    "A control runs inside a worker process holding a transaction-scoped lock, and nothing in "
    "this repository ends one. brain.ops.jobs moves a job through cancelling and nothing stores "
    "the row it moves; the queue driver's cancellation is called by nothing and its table cannot "
    "be read from here; brain.ops.halt stops new work being admitted rather than a run in "
    "progress, and no route serves it. A stop button reaching none of these is refused or "
    "ignored every time it is pressed, which teaches a person that stopping does not work on "
    "the day it matters."
)

#: Why the models response leaves out what other routes already answer.
A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE: Final = (
    "The routing chain, the latency against its objective and the cost are each served by a "
    "route with its own grant and its own decision about who may read them. Copying any of them "
    "onto this response would put one set of rows behind two grants, and the day the two grants "
    "differ is the day one screen shows what the other refuses. The page asks those routes and "
    "draws what each one says, including a refusal."
)

#: Why the fallbacks figure is a sum the ledger holds rather than something counted here.
FALLBACKS_ARE_THE_LEDGERS_SUM_OVER_THE_WINDOW: Final = (
    "A fallback is counted by the executor on the request it happened in and written to that "
    "request's ledger row. The figure is the database's sum of that column over the window, over "
    "the whole install, served only to a reader whose basis is everybody's, so it is a sum of "
    "rows the reader may see all of and not a figure narrowed from a larger one."
)


# ----------------------------------------------------------------- the screens

#: The screen whose grant decides whether the models answer opens at all. A key rather than a
#: capability, so the registry stays the one statement of what the screen needs.
MODELS_SCREEN: Final = "models"


# ------------------------------------------------------------------ the bounds

#: What the models window covers when nobody says. Seven days, the design's own window, and
#: inside `brain.report_routes.MAX_READING_HOURS` so the page can ask the service-level route for
#: the same span in the same unit.
DEFAULT_WINDOW_HOURS: Final = 24 * 7

#: The longest window one request may ask for: the service-level route's bound, imported rather
#: than restated, so the page's two requests cannot be bounded differently.
MAX_WINDOW_HOURS: Final = MAX_READING_HOURS

#: The measurements the models screen draws that the metadata ledger cannot yet fill, by the
#: ledger's own field names. The reason each is missing is `UNFILLABLE_TODAY`'s and is read there.
MEASURES_THE_MODELS_SCREEN_DRAWS: Final[tuple[str, ...]] = ("model", "provider", "fallback_count")

#: What each tier is for, in the words a person choosing a rung needs.
#:
#: Keyed by `brain.models.routing.Tier` and tested to cover every member, so a tier added there is
#: a failing test here rather than a row with no description. Written from `classify_tier`'s own
#: precedence rather than from the design's lanes: the design draws lanes and the chain is kept
#: by tier, and the page says which it is showing.
TIER_HANDLES: Final[Mapping[Tier, str]] = MappingProxyType(
    {
        Tier.NONE: "The fast lane: exact lookups answered from the projection, with no model",
        Tier.SMALL: "Cheap sub-steps, never a tool loop and never a residency-constrained scope",
        Tier.MAIN: "Questions needing judgement, and any request nothing pins elsewhere",
        Tier.HEAVY: "Task work and requests too large for the main pool's window",
    }
)


# ------------------------------------------------------------------- the shapes


class RunningControlView(BaseModel):
    """One control running now, as `brain.console.operate.ControlRun` has it.

    `keeps_true` is the control's own `guards` sentence from `brain.ops.controls`, so a person
    reading a control name they do not recognise is told what stops holding if it stops running.
    It is product text, identical on every install.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    keeps_true: str
    started_at: datetime
    report_only: bool
    stalled: bool


class OwedControlView(BaseModel):
    """One control owed a run and not yet started, as `OwedControl` has it.

    `late_by_seconds` rather than a duration string, so the console formats it and a test can
    compare it with a number.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    keeps_true: str
    due_since: datetime
    late_by_seconds: float
    first_run: bool


class LiveRunsView(BaseModel):
    """What is running and what is waiting, over the rows this reader may see.

    No count and no total: a count beside a filtered list is the size of what was withheld, and
    the lists are short enough to read. `as_of` is the instant the request was admitted, so the
    page measures how long a run has been going against the server's clock rather than the
    browser's.

    The three booleans are always true today and are fields rather than console sentences, which
    is `brain.skill_routes.SkillsPage`'s construction: the fact belongs to the API that knows it,
    and the day one stops being true it goes false in the commit that changes it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    running: list[RunningControlView]
    waiting: list[OwedControlView]
    #: The scheduler's own line for asking whether a run is still alive, in seconds.
    stalled_after_seconds: float
    #: Questions and agent runs are recorded when they finish, so nothing in flight is listed.
    #: See `A_SCREEN_OF_RUNS_SHOWS_THE_RUNS_SOMETHING_RECORDS_AND_SAYS_WHICH_ONES_NOTHING_DOES`.
    requests_in_flight_are_not_recorded: bool = True
    #: The queue driver's rows are refused to the application. See
    #: `THE_QUEUE_IS_NOT_THE_APPLICATIONS_TO_READ`.
    queue_is_not_readable: bool = True
    #: Nothing here can stop a run. See `NO_RUN_CAN_BE_STOPPED_FROM_HERE`.
    no_run_can_be_stopped: bool = True


class TierView(BaseModel):
    """One routing tier and what it is for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    handles: str


class LaneTrafficView(BaseModel):
    """How many requests one lane finished in the window, over the whole install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane: str
    requests: int


class ProviderView(BaseModel):
    """One provider this system holds a key slot for. Never a key, and never whether one is held.

    `brain.ops.provider_keys.PROVIDER_SLOTS`, which is closed: a provider that can be configured
    but was never argued about is a provider whose key nobody decided to trust. The environment
    variable a slot fills is left out, because a screen has no use for it and a name that tells a
    reader where a secret lives is a step towards reading it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    description: str


class UnmeasuredView(BaseModel):
    """A measurement the screen draws that nothing fills, and the ledger's own reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measure: str
    because: str


class ModelsView(BaseModel):
    """What the models screen needs that only this route knows.

    Everything here is over the whole install and is served only to a reader whose basis for the
    models screen is everybody's, so no figure on it is a subtraction from a narrower one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    tiers: list[TierView]
    #: Every lane, zero included: a lane is a closed vocabulary of this product and a missing row
    #: would read as a lane this install does not have.
    lanes: list[LaneTrafficView]
    providers: list[ProviderView]
    unmeasured: list[UnmeasuredView]
    #: How many times a request in the window moved to a later rung after a failure, summed from
    #: the ledger. See `FALLBACKS_ARE_THE_LEDGERS_SUM_OVER_THE_WINDOW`.
    fallbacks_fired: int


# ---------------------------------------------------------------- the statements


def newest_run_of_each_control() -> Select[tuple[str, datetime, datetime | None, bool]]:
    """Each control's newest run, whether or not it finished.

    The newest run overall and then the unfinished ones among them, rather than the newest
    unfinished run, and the difference is a run that died. `brain.ops.schedule_store.unfinished`
    asks the second question, which is right for the scheduler and wrong here: a control whose run
    died at one and ran cleanly at two has an unfinished row at one for ever, and a live screen
    listing it would say the control is running now.

    `DISTINCT ON` the name with the start descending, which is `last_attempts`' construction, so
    this is one row per control whatever the table holds.
    """
    return (
        select(
            ControlRunRow.name,
            ControlRunRow.started_at,
            ControlRunRow.finished_at,
            ControlRunRow.report_only,
        )
        .order_by(ControlRunRow.name, ControlRunRow.started_at.desc())
        .distinct(ControlRunRow.name)
    )


def requests_by_lane(start: datetime, end: datetime) -> Select[tuple[str, int]]:
    """How many requests each lane finished in `[start, end)`, counted by the database.

    A count grouped in SQL rather than every row fetched and counted here, which is what
    `brain.ops.telemetry_store.observed_between` does for a percentile that needs the rows: this
    needs a number per lane, and seven days of a busy install is not a list to carry into a
    process for that. The lane and the count, and no column that names a person.
    """
    return (
        select(RequestTelemetryRow.lane, func.count())
        .where(RequestTelemetryRow.received_at >= start, RequestTelemetryRow.received_at < end)
        .group_by(RequestTelemetryRow.lane)
    )


def fallbacks_between(start: datetime, end: datetime) -> Select[tuple[int | None]]:
    """The sum of every fallback the ledger recorded in `[start, end)`, zero when there is none.

    Summed by the database, for `requests_by_lane`'s reason, and coalesced there, because a sum
    over no rows is null and a window in which nothing fell back is a measured zero: every request
    that called a model recorded its count, and a request that called none fell back from nothing.
    """
    return select(
        func.coalesce(func.sum(RequestTelemetryRow.fallback_count), 0).label("fallbacks")
    ).where(RequestTelemetryRow.received_at >= start, RequestTelemetryRow.received_at < end)


# ------------------------------------------------------------------ the projections


def _declared(controls: Sequence[Control]) -> dict[str, Control]:
    return {one.name: one for one in controls}


def running_from(
    rows: Sequence[tuple[str, datetime, datetime | None, bool]],
    *,
    now: datetime,
    controls: Sequence[Control] = CONTROLS,
) -> tuple[list[tuple[str, datetime, bool]], tuple[str, ...]]:
    """The unfinished newest runs, and which of those the scheduler would call stalled.

    A row naming a control the registry no longer declares is dropped. The check constraint on
    the table is generated from the registry when a migration runs, so a control retired since
    leaves rows the constraint still admits, and a retired control is not running whatever its
    last row says.
    """
    known = _declared(controls)
    started = [
        (name, at, report_only)
        for name, at, finished_at, report_only in rows
        if finished_at is None and name in known
    ]
    return started, stalled_runs({name: at for name, at, _ in started}, now=now)


def running_view(run: ControlRun, controls: Sequence[Control] = CONTROLS) -> RunningControlView:
    """One running control, copied field by field, with the registry's sentence beside it."""
    return RunningControlView(
        control=run.control,
        keeps_true=_declared(controls)[run.control].guards,
        started_at=run.started_at,
        report_only=run.report_only,
        stalled=run.stalled,
    )


def waiting_view(owed: OwedControl, controls: Sequence[Control] = CONTROLS) -> OwedControlView:
    """One owed control, copied field by field, with the registry's sentence beside it."""
    return OwedControlView(
        control=owed.control,
        keeps_true=_declared(controls)[owed.control].guards,
        due_since=owed.due_since,
        late_by_seconds=owed.late_by.total_seconds(),
        first_run=owed.first_run,
    )


def lane_traffic(counted: Sequence[tuple[str, int]]) -> list[LaneTrafficView]:
    """Every lane in the order `Lane` declares it, with the count the database gave or zero.

    A lane the ledger holds that `Lane` does not declare is dropped rather than shown: the table's
    check constraint is generated from `Lane`, so such a row is a lane since retired, and a
    renamed lane shown under its old name beside its new one would split one figure in two.
    """
    found = dict(counted)
    return [LaneTrafficView(lane=one.value, requests=found.get(one.value, 0)) for one in Lane]


def provider_views(slots: Sequence[ProviderSlot] = PROVIDER_SLOTS) -> list[ProviderView]:
    """Every provider slot, in the order the slots are declared, with no key and no variable."""
    return [ProviderView(provider=one.slug, description=one.description) for one in slots]


def unmeasured(
    unfillable: Mapping[str, str] = UNFILLABLE_TODAY,
    measures: Sequence[str] = MEASURES_THE_MODELS_SCREEN_DRAWS,
) -> list[UnmeasuredView]:
    """The measurements this screen draws that the ledger cannot fill, with the ledger's reason.

    Read out of `UNFILLABLE_TODAY` rather than written here, so the day `provider` is filled its
    entry leaves that mapping and its sentence leaves this screen in the same commit, rather than
    a console sentence going on saying no model is called after one is.
    """
    return [
        UnmeasuredView(measure=one, because=unfillable[one])
        for one in measures
        if one in unfillable
    ]


def tier_views() -> list[TierView]:
    """Every tier in the order `Tier` declares it, with what it is for."""
    return [TierView(tier=one.value, handles=TIER_HANDLES[one]) for one in Tier]


# ------------------------------------------------------------------- the wiring


def sessions_of(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """The session factory this process was built with, or None, in `routing_routes`' shape."""
    found = getattr(request.app.state, "db_sessions", None)
    return found if isinstance(found, async_sessionmaker) else None


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault, identically for every caller who reaches it.

    A `Failed` rather than an `Absent`, on `brain.routing_routes`' argument: an instance with no
    pool is broken rather than idle, and an empty live runs page there would read as nothing
    running.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _models_not_answerable() -> Absent:
    """The one refusal this router makes. Names the screen and never the caller or the grant."""
    return Absent(f"the {MODELS_SCREEN} screen is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["operate"])


@router.get("/operate/runs", response_model=LiveRunsView, responses=COMMON_RESPONSES)
async def live_runs(request: Request, asked: Asked) -> LiveRunsView:
    """What is running now and what is owed a run, as this reader may see them.

    Read for everybody and narrowed by `brain.console.operate`, in that order, which is
    `brain.report_routes`' construction: a reader without either screen's grant is answered two
    empty lists, which is exactly what an install running nothing produces, and nothing on the
    response says a narrowing happened.

    Two statements. The newest run of each control, which gives both what is running and when
    each control was last tried; and the last success of each, which is the second clock
    `due_now` needs so a control failing every run is reported late rather than on time.
    """
    factory = _require_sessions(request)
    async with factory() as session:
        found = await session.execute(newest_run_of_each_control())
        rows = [row._tuple() for row in found.all()]
        succeeded = await last_successes(session)

    now = asked.now
    started, stalled = running_from(rows, now=now)
    attempted = {name: at for name, at, _, _ in rows}
    owed = due_now(now=now, last_attempt=attempted, last_success=succeeded)
    running = unattended_running(started, stalled, asked.reach, now)

    return LiveRunsView(
        as_of=now,
        running=[running_view(one) for one in running],
        waiting=[waiting_view(one) for one in unattended_waiting(owed, asked.reach, now)],
        stalled_after_seconds=STALLED_AFTER.total_seconds(),
    )


@router.get("/operate/models", response_model=ModelsView, responses=COMMON_RESPONSES)
async def models(
    request: Request,
    asked: Asked,
    hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = DEFAULT_WINDOW_HOURS,
) -> ModelsView:
    """The models screen's own figures and sentences, for a reader who may see everybody's.

    The basis first and the database second, and the order is the property: a caller whose basis
    is their own is refused identically on an instance with a database and on one without, so
    nobody reads this deployment's state off the difference between a refusal and a fault.

    The window ends at the instant the request was admitted, for
    `brain.report_routes.service_levels`' reason: a traffic figure is a sum over the whole
    install, and an end the caller chose would be a narrowing nobody decided on.
    """
    if figure_basis(panel(MODELS_SCREEN), asked.reach, asked.now) is not Basis.EVERYONE:
        log.info("models screen not answerable", principal=asked.caller.principal.id)
        raise _models_not_answerable()

    factory = _require_sessions(request)
    start = asked.now - timedelta(hours=hours)
    async with factory() as session:
        found = await session.execute(requests_by_lane(start, asked.now))
        counted = [row._tuple() for row in found.all()]
        fell_back = (await session.execute(fallbacks_between(start, asked.now))).scalar_one()

    return ModelsView(
        start=start,
        end=asked.now,
        tiers=tier_views(),
        lanes=lane_traffic(counted),
        providers=provider_views(),
        unmeasured=unmeasured(),
        fallbacks_fired=int(fell_back or 0),
    )
