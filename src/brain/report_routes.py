"""The Report screens over HTTP: service levels, spend, adoption, usage, questions and quality.

`brain.console.service_level_view`, `brain.console.spend_report_view` and
`brain.console.adoption_view` each decide what one reader may be shown, and each says in its
own docstring that nothing renders it. `brain.ops.console_screens` counts that as a screen
nobody has: the tracker closed the leaf on the day the decision was written rather than on the
day somebody could open it. This is the half that makes them reachable, and it decides nothing.

The second three arrived on 2026-09-16 and are the design's own Report section: `docs/screens.html`
draws Questions and gaps, Usage and cost, and Quality and canaries under Report on the company
overview. `brain.console.usage_screen`, `brain.console.questions_view` and
`brain.console.quality_view` decide them, and each of those says in its own docstring how much of
the design an install can support today, which for all three is less than the design draws. The
routes carry what they decide and nothing more; see
`A_SCREEN_THAT_CANNOT_SHOW_A_FIGURE_SAYS_SO_ON_THE_RESPONSE` for the flags that carry the rest.

**Every figure on these responses is the read module's, and this module computes none of
them.** No total is summed here, no line is dropped here, no department is looked up here and
no window is narrowed here. What this module does is read a store, hand the rows and the
caller's reach to the module that owns the decision, and copy the answer field by field onto a
response model. The one thing it adds is a bound on what a caller may ask for, which is a
resource limit rather than a permission. See `THE_READ_MODULE_DECIDES_AND_THIS_ROUTE_COPIES`.

**There is no capability check in front of these three, and its absence is the design rather
than an omission.** `brain.routing_routes` checks `MATRIX_READ` before it looks at the
database, and the reason it gives is exact: the matrix is one yes or no, so a capability is the
whole of the decision and asking it first keeps the deployment's state out of an unentitled
caller's answer. Not one of these three screens is one yes or no. A spend report is filtered
row by row through `may_read_spend`, an adoption line exists for every department that predicate
admits, and a reading is narrowed by `may_read_service_levels` against a row with no fields. A
capability checked here as well would be a second copy of the first half of each of those
predicates, sitting in front of them, and the copy in front is the one that drifts when the
predicate behind it widens. So the route asks nothing and the read module answers everything,
and a reader holding no usage grant is shown an empty report rather than a refusal, which is
what all three modules argue for in their own words. See
`A_SECOND_COPY_OF_A_ROW_PREDICATE_IN_FRONT_OF_IT_IS_THE_COPY_THAT_DRIFTS`.

**A refused reader and a reader of a quiet install get equal objects, and the refusal is
therefore not visible as one.** That is `service_level_view.A_REFUSED_READING_IS_THE_READING_OF_
AN_INSTALL_THAT_PROMISES_NOTHING` carried to the wire without softening: a department-scoped
caller reads a window with no lanes on it, which is exactly what an install declaring no
objectives produces, and nothing on the response says a narrowing happened. The same shape holds
for the other two: fewer lines, no note, no residual bucket and no count.

**The database is read before the decision is taken, for all three, and that is deliberate.**
`A_REFUSED_READ_DOES_THE_SAME_WORK_AS_A_PERMITTED_ONE` is the argument and it applies here
literally: a route that returned early for a reader it expected to be refused would stop
refusing a malformed window and a database that cannot answer, so the refused reader would be
the one reader whose broken request succeeded, and the difference in latency would be readable
from outside. A process with no pool answers the same fault to everybody.

**A breakdown is not paged, and that is the one place this module refuses to follow the
matrix's shape.** `brain.routing_routes.RungPage` carries `truncated`, which says the page came
back full and carries no arithmetic. A spend report cannot do that, because
`brain.console.spend_view.Report` asserts its total is the sum of its own lines and the whole
argument for that assertion is that a renderer handed a truncated list prints a figure nobody
can reconcile. Sending a bounded set of lines beside the unbounded total would put exactly that
subtraction on the wire. So the spend response carries every line the read module produced,
with its total, and the bound this route applies is on the window rather than on the lines. See
`A_BREAKDOWN_CANNOT_BE_PAGED_WHILE_ITS_TOTAL_IS_ON_IT`.

Adoption is paged, because an adoption line carries no total to reconcile against: each line is
a department's own two figures and the answer holds no sum over them. So `AdoptionPage` is
`RungPage`'s shape exactly, `truncated` is the page having come back full, and there is no
`total` populated and no count of departments beyond it.

**One router for the Report section rather than one per screen.** `brain.app` argues a second
router by the refusals differing, and these do not differ: every one of them is a read with no
write verb, decided row by row or fact by fact in a module under `brain.console`, answering an
empty figure rather than an error. Usage is read under the same usage grant as the first three.
Questions and quality are read under their own screens' grants, `read:question` and
`read:evaluation`, and the refusal is still the same shape: a reader who may not be told is
answered as an install with nothing to tell, and nothing on the response says which. So the
section is one router, and a second one would be the same two sentences of wiring again. The
alternative that was rejected outright is mounting these on `brain.api_routes`, for the reason
`routing_routes` rejects it: that module's rules are about entities and enumeration, and a report
is neither.

**What has never run.** This repository has no PostgreSQL, so none of the SELECTs below has been
executed. What is tested is the statements `live_departments` and `last_canary_run` compile to,
the read modules' own decisions over rows built in memory, and the shape of every response. The
store reads are unverified against a server and are the first thing to exercise against one.

Of the second three, M27.7.14, M27.7.18 and M27.7.19 are claimed here for what the screens can
show and are closed by none of them, for the reasons each read module gives.

Task ids: M27.7.14, M27.7.15, M27.7.16, M27.7.17, M27.7.18, M27.7.19
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.adoption import DepartmentAdoption
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, row_readers
from brain.console.adoption_view import adoption_for_reader
from brain.console.quality_view import (
    CANARY_CONTROL,
    EVALUATION_RUNS_ARE_RECORDED,
    FINDINGS_ARE_RECORDED,
    CanaryRun,
    QualityScreen,
    canary_run_of,
    quality_for_reader,
)
from brain.console.questions_view import (
    UNANSWERED_QUESTIONS_ARE_RECORDED,
    QuestionsScreen,
    questions_for_reader,
)
from brain.console.service_level_view import service_levels_for_reader
from brain.console.spend_report_view import MaterialisedReport, spend_report_from_view
from brain.console.usage_screen import AUTOMATION_IS_COUNTED, UsageScreen, usage_for_reader
from brain.core.errors import Failed
from brain.ops.question_store import asked_between
from brain.ops.schedule_runner import runner_for
from brain.ops.service_levels import LaneReading, ServiceLevels
from brain.ops.spend import Dimension
from brain.ops.spend_store import read_spend_daily
from brain.ops.telemetry_store import metered_between
from brain.tables.gate import DepartmentRow
from brain.tables.schedule import ControlRunRow
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why no figure on any of these responses is computed here.
THE_READ_MODULE_DECIDES_AND_THIS_ROUTE_COPIES: Final = (
    "Each of these three screens has a module under brain.console that decides what a reader "
    "may be shown, and each of those modules holds an argument about what a figure beside a "
    "filtered one discloses. A route that summed a total, dropped a line or resolved a "
    "department would be taking one of those decisions a second time, one layer out, where "
    "the argument is not written down. So the route reads a store, hands the rows and the "
    "reach to the module, and copies what comes back field by field."
)

#: Why these routes hold no capability check of their own.
A_SECOND_COPY_OF_A_ROW_PREDICATE_IN_FRONT_OF_IT_IS_THE_COPY_THAT_DRIFTS: Final = (
    "brain.routing_routes checks a capability before it reads, and its reason is that the "
    "matrix is one decision for the whole collection. These three are not: a spend line is "
    "admitted by may_read_spend, an adoption line by the same predicate over a department "
    "name, and a reading by may_read_service_levels against a row with no fields. Asking for "
    "the capability here as well would put the first half of each predicate in front of it, "
    "and a widened predicate behind a narrower copy in front is a screen that goes empty for "
    "a reader who may read it, with nothing saying which of the two answered."
)

#: Why the spend response carries every line the read module produced.
A_BREAKDOWN_CANNOT_BE_PAGED_WHILE_ITS_TOTAL_IS_ON_IT: Final = (
    "brain.console.spend_view.Report asserts that its total is the sum of its own lines, "
    "because a renderer handed a truncated list prints a figure nobody can reconcile. A page "
    "of lines beside that total is that truncated list with the figure already computed: the "
    "total less the lines shown is the cost of the rows the page left out. So a breakdown is "
    "answered whole and the bound this route applies is on the window it covers, which is a "
    "resource limit and changes no figure on the page."
)

#: Why a window is bounded at all, and what the bound is not.
A_WINDOW_BOUND_IS_A_RESOURCE_LIMIT_AND_NEVER_A_PERMISSION: Final = (
    "A request naming a window of ten years reads every row the store holds and groups them "
    "in one process, and nothing about the caller makes that cheaper. The bounds below exist "
    "so one request cannot ask for an unbounded read, and they are identical for every "
    "caller: a reader refused every row and a reader admitted every row are bounded the same, "
    "so nothing about what somebody may see can be worked out from which windows they may ask "
    "for."
)

#: Why the second three responses carry flags about what is not recorded.
A_SCREEN_THAT_CANNOT_SHOW_A_FIGURE_SAYS_SO_ON_THE_RESPONSE: Final = (
    "The design draws tokens, unanswered questions and a green canary light, and no ledger on an "
    "install holds any of them. A response that simply left them out would render as a screen "
    "saying there were none, which is a figure and a false one. So each response carries what "
    "its read module says is not measured or not recorded, copied from that module's constant "
    "or its answer, and the page says it in words. The flags are the product's facts and are "
    "the same for every reader, so they say nothing about what any reader was withheld."
)


# ------------------------------------------------------------------------ the bounds

#: The longest service level window one request may ask for, in hours. Four weeks, which is
#: past any lane's objective period and well inside what one read of `obs.request_telemetry`
#: can group. See `A_WINDOW_BOUND_IS_A_RESOURCE_LIMIT_AND_NEVER_A_PERMISSION`.
MAX_READING_HOURS: Final = 24 * 28

#: What a reading covers when nobody says. A day, because a lane's attainment over a shorter
#: window is a sample and over a longer one is a month somebody has to divide by hand.
DEFAULT_READING_HOURS: Final = 24

#: The longest adoption window one request may ask for, in days. A year, because adoption is
#: read to answer who has stopped using the system and a quarter is too short to tell.
MAX_ADOPTION_DAYS: Final = 366

#: What an adoption window covers when nobody says.
DEFAULT_ADOPTION_DAYS: Final = 30

#: How many adoption lines one page carries at most. One line per department in the reader's
#: reach, so this is far above any real company's list and exists so one request cannot ask
#: for an unbounded page.
MAX_ADOPTION_LINES: Final = 500

#: What a caller gets when they do not say. Above any plausible department list, so
#: `truncated` is false in practice.
DEFAULT_ADOPTION_LINES: Final = 200

#: The longest usage window one request may ask for, in days. A year, for adoption's reason:
#: the question somebody brings to a usage screen is often who stopped asking.
MAX_USAGE_DAYS: Final = 366

#: What a usage window covers when nobody says. A week, which is the window the design's own
#: overview draws beside its figures.
DEFAULT_USAGE_DAYS: Final = 7


# ------------------------------------------------------------------------ the shapes


class LaneReadingView(BaseModel):
    """One lane's measured attainment beside what it promised.

    Every field is `brain.ops.service_levels.LaneReading`'s own, and `met` is its property
    rather than a comparison made here: a route deciding whether a lane met its objective
    would be a second implementation of the shortfall rule, and the two would disagree about
    a lane the day either threshold moved.

    `shortfalls` is carried whole and unrendered. They are sentences the reliability module
    composed about this install's own lanes, they name no department and no person, and
    summarising them here would be this module inventing a vocabulary for a structure that
    already has one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane: str
    #: What the lane promises, so a reader can see the gap without holding a second document.
    objective_p95_ms: int | None
    objective_success_rate: float
    #: What was measured. Null where the sample could not support a rank, which is
    #: `brain.ops.service_levels`'s decision and not an absent value.
    p95_ms: float | None
    success_rate: float | None
    requests: int
    met: bool
    shortfalls: list[str]


class ServiceLevelsView(BaseModel):
    """A reading of the whole install over one window, or the same window with no lanes.

    There is no field here saying which of the two this is, and that is the property the
    screen turns on: `service_level_view.for_reader` answers a refused reader the reading an
    install declaring no objectives produces over a quiet window, so a refusal and an install
    that promises nothing are equal objects. A boolean saying `narrowed` would undo that in
    one field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    lanes: list[LaneReadingView]


class SpendLineView(BaseModel):
    """One bucket of a spend breakdown: what it is called and what it cost.

    `brain.console.spend_view.Line`, field for field. Minor units, because that is what the
    ledger holds and a currency conversion on a reporting path is a second opinion about a
    price.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    cost_minor: int


class SpendReportView(BaseModel):
    """A spend breakdown in one dimension, with the age of the figures on it.

    `total_minor` is the sum of `lines` and is not recomputed here: it is copied off
    `brain.console.spend_view.Report`, whose constructor asserts the equality. Every line the
    reader may see is present, so the copy is faithful rather than a total over a page. See
    `A_BREAKDOWN_CANNOT_BE_PAGED_WHILE_ITS_TOTAL_IS_ON_IT`.

    `as_of` and `freshness` are `brain.console.spend_report_view.MaterialisedReport`'s fields
    and are on the object rather than left to a caption, which is that module's
    `STALENESS_IS_A_FIGURE_ON_THE_REPORT_AND_NEVER_A_CAPTION`.

    `built` is false exactly when the view has never been refreshed, and then there are no
    lines and no total at all rather than zeroes: a report over nothing says the company spent
    nothing, which is a figure and a false one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str
    built: bool
    lines: list[SpendLineView]
    machine_included: bool
    total_minor: int | None
    as_of: datetime | None
    #: LIVE, AGEING, STALE or UNSTATED, on `brain.gate.provenance`'s scale and no other.
    freshness: str


class AdoptionLineView(BaseModel):
    """One department's adoption over a window: questions asked, and who asked them.

    `brain.adoption.DepartmentAdoption`, field for field. There is nowhere here for a fourth
    figure, which is that dataclass's own rule carried onto the wire.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    questions: int
    people: int


class AdoptionPage(Page[AdoptionLineView]):
    """The adoption lines this reader may see, as one page.

    `total` is inherited and never populated, for the reason every listing here gives: a count
    beside a filtered list is the size of what the reader was not shown.

    `truncated` is the page having come back full and never how much more there is, which is
    `brain.routing_routes.RungPage`'s flag and its argument. `next_cursor` is always null:
    the lines are ordered by department name and a keyset cursor over that is expressible, so
    this is a gap rather than an impossibility, and a small one while a page holds two hundred
    departments.
    """

    truncated: bool = False


class DepartmentUsageView(BaseModel):
    """One department's questions and askers on the usage screen, field for field.

    `brain.adoption.DepartmentAdoption`, the same line adoption draws, because the usage
    screen's department table is that measure over the same chosen questions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    questions: int
    people: int


class PersonUsageView(BaseModel):
    """One person's questions on the usage screen. `brain.console.usage_screen.PersonLine`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person: str
    questions: int


class TokenLineView(BaseModel):
    """One bucket of one token breakdown. `brain.console.usage_view.UsageLine`, field for field.

    `runs` is how many requests with a model call fell in the bucket, which is the figure the
    tokens are over; it is not a count of questions and the page does not call it one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    runs: int
    tokens_in: int
    tokens_out: int


class TokenBreakdownView(BaseModel):
    """Tokens by one axis. `brain.console.usage_view.UsageReport`, whose totals are its lines'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    axis: str
    lines: list[TokenLineView]
    total_runs: int
    total_tokens_in: int
    total_tokens_out: int


class UsageView(BaseModel):
    """The usage screen for one reader over one window.

    Not a `Page`: `questions` is asserted by `brain.console.usage_screen.UsageScreen` to be the
    sum of every table under it, so the lines are carried whole, which is
    `A_BREAKDOWN_CANNOT_BE_PAGED_WHILE_ITS_TOTAL_IS_ON_IT` again. The window bounds how many.

    `departments`, `people` and `questions` are null exactly when the read module offered this
    reader no axis. `not_measured` names what the screen is asked for and no ledger fills, in
    the read module's words; see `A_SCREEN_THAT_CANNOT_SHOW_A_FIGURE_SAYS_SO_ON_THE_RESPONSE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    departments: list[DepartmentUsageView] | None
    people: list[PersonUsageView] | None
    questions: int | None
    machine_included: bool
    not_measured: list[str]
    #: Tokens by each axis this reader may break usage down by, in the leaf's order. An axis
    #: withheld is absent, and nothing says so. See `brain.console.usage_screen`.
    tokens: list[TokenBreakdownView]


class QuestionsView(BaseModel):
    """The questions screen for one reader. `brain.console.questions_view.QuestionsScreen`.

    `nothing_connected` is false both on an install with a source connected and for a reader who
    may not be told, and there is no field saying which. The two sentences are the answer lane's
    own, carried so the page quotes what askers receive rather than a copy of it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    nothing_connected: bool
    answered_when_nothing_connected: str
    answered_when_nothing_found: str
    unanswered_are_recorded: bool


class CanaryRunView(BaseModel):
    """One attempt to run the canaries. `brain.console.quality_view.CanaryRun`, field for field.

    `state` is finished, failed, declined or unfinished, and never passed: see
    `brain.console.quality_view.A_FINISHED_RUN_IS_NOT_A_GREEN_ONE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: datetime
    finished_at: datetime | None
    state: str


class QualityView(BaseModel):
    """The quality screen for one reader. `brain.console.quality_view.QualityScreen`.

    `last_canary_run` is null both when no run is recorded and when this reader may not see one,
    and nothing else on the response differs between the two.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    last_canary_run: CanaryRunView | None
    canaries_started: bool
    canary_interval_seconds: int
    findings_are_recorded: bool
    evaluation_runs_are_recorded: bool


def usage_screen_view_of(screen: UsageScreen) -> UsageView:
    """The usage screen, copied field by field, with the absent axes carried as null."""
    return UsageView(
        start=screen.start,
        end=screen.end,
        departments=None
        if screen.departments is None
        else [
            DepartmentUsageView(
                department=one.department, questions=one.questions, people=one.people
            )
            for one in screen.departments
        ],
        people=None
        if screen.people is None
        else [PersonUsageView(person=one.person, questions=one.questions) for one in screen.people],
        questions=screen.questions,
        machine_included=AUTOMATION_IS_COUNTED,
        not_measured=[one.value for one in screen.not_measured],
        tokens=[
            TokenBreakdownView(
                axis=report.axis.value,
                lines=[
                    TokenLineView(
                        key=line.key,
                        runs=line.runs,
                        tokens_in=line.tokens_in,
                        tokens_out=line.tokens_out,
                    )
                    for line in report.lines
                ],
                total_runs=report.total_runs,
                total_tokens_in=report.total_tokens_in,
                total_tokens_out=report.total_tokens_out,
            )
            for report in screen.tokens
        ],
    )


def questions_view_of(screen: QuestionsScreen) -> QuestionsView:
    """The questions screen, copied field by field."""
    return QuestionsView(
        nothing_connected=screen.nothing_connected,
        answered_when_nothing_connected=screen.answered_when_nothing_connected,
        answered_when_nothing_found=screen.answered_when_nothing_found,
        unanswered_are_recorded=UNANSWERED_QUESTIONS_ARE_RECORDED,
    )


def canary_run_view_of(run: CanaryRun) -> CanaryRunView:
    """One canary run, copied field by field."""
    return CanaryRunView(
        started_at=run.started_at, finished_at=run.finished_at, state=run.state.value
    )


def quality_view_of(screen: QualityScreen) -> QualityView:
    """The quality screen, copied field by field."""
    return QualityView(
        last_canary_run=None
        if screen.last_canary_run is None
        else canary_run_view_of(screen.last_canary_run),
        canaries_started=screen.canaries_started,
        canary_interval_seconds=screen.canary_interval_seconds,
        findings_are_recorded=FINDINGS_ARE_RECORDED,
        evaluation_runs_are_recorded=EVALUATION_RUNS_ARE_RECORDED,
    )


def lane_view_of(reading: LaneReading) -> LaneReadingView:
    """One lane's reading, copied field by field.

    Written out rather than built from the dataclass's fields, for the reason
    `brain.routing_routes.view_of` gives about its own: a field added to `LaneReading` would
    otherwise arrive in a response because a copy loop was generous.
    """
    return LaneReadingView(
        lane=reading.objective.lane.value,
        objective_p95_ms=reading.objective.p95_ms,
        objective_success_rate=reading.objective.success_rate,
        p95_ms=reading.p95_ms,
        success_rate=reading.success_rate,
        requests=reading.requests,
        met=reading.met,
        shortfalls=list(reading.shortfalls),
    )


def reading_view_of(levels: ServiceLevels) -> ServiceLevelsView:
    """A whole reading, in the objectives' declared order, which is the order it arrives in."""
    return ServiceLevelsView(
        start=levels.start,
        end=levels.end,
        lanes=[lane_view_of(one) for one in levels.lanes],
    )


def spend_view_of(report: MaterialisedReport, dimension: Dimension) -> SpendReportView:
    """A materialised report, copied field by field, including the case with no report in it.

    The `None` report is carried as `built=False` with no lines and no total rather than as an
    empty report, which is
    `brain.console.spend_report_view.A_REPORT_NOBODY_HAS_BUILT_IS_NOT_A_REPORT_OF_NOTHING` on
    the wire. `machine_included` then has nothing to describe and is false, which is the
    default the request was made with when no report came back.
    """
    if report.report is None:
        return SpendReportView(
            dimension=dimension.value,
            built=False,
            lines=[],
            machine_included=False,
            total_minor=None,
            as_of=None,
            freshness=report.freshness.state.value,
        )
    return SpendReportView(
        dimension=dimension.value,
        built=True,
        lines=[
            SpendLineView(key=one.key, cost_minor=one.cost_minor) for one in report.report.lines
        ],
        machine_included=report.report.machine_included,
        total_minor=report.report.total_minor,
        as_of=report.as_of,
        freshness=report.freshness.state.value,
    )


def adoption_view_of(line: DepartmentAdoption) -> AdoptionLineView:
    """One adoption line, copied field by field."""
    return AdoptionLineView(
        department=line.department, questions=line.questions, people=line.people
    )


# ---------------------------------------------------------------------- the statements


def live_departments() -> Select[tuple[str]]:
    """Every live department's slug, in name order.

    The directory's own list rather than the departments the records happen to mention, which
    is `brain.console.adoption_view.THE_DEPARTMENTS_ARE_THE_DIRECTORYS_AND_NOT_WHATEVER_WAS_
    RECORDED`: a list built from who asked gives a line to a department whose only traffic was
    a schedule's and none to a department where nobody asked anything, and a reader learns both
    from which lines appear.

    `deleted_at IS NULL` here as well as in the row-level policy, on `live_rungs`' argument: a
    statement whose correctness depends on a policy being installed is a statement that is
    wrong on a database restored without one.

    The slug and not the row. A department's name, its company and its scope slug are all
    facts this screen has no use for, and a select of the row would carry them to a caller who
    asked how many questions were asked.
    """
    return (
        select(DepartmentRow.slug)
        .where(DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
    )


def last_canary_run() -> Select[tuple[datetime, datetime | None, str | None]]:
    """The newest attempt to run the canaries: when it started, when it ended, and how.

    Three columns and not the row. `ops.control_run.detail` is a sentence for an operator, and a
    canary run's sentence is where a finding would be written the day a runner writes one; a
    field name there is the content `brain.console.operate.findings_in_reach` exists to filter,
    so it is never selected rather than selected and dropped.

    Newest by start rather than by finish, so a run that started and never returned is the
    answer when it is the latest thing that happened, which is `unfinished` on the screen rather
    than an older finished run standing in for it.
    """
    return (
        select(ControlRunRow.started_at, ControlRunRow.finished_at, ControlRunRow.outcome)
        .where(ControlRunRow.name == CANARY_CONTROL)
        .order_by(ControlRunRow.started_at.desc())
        .limit(1)
    )


# ------------------------------------------------------------------------- the wiring


def sessions_of(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """The session factory this process was built with, or None.

    `getattr` and an `isinstance`, in the shape `brain.routing_routes.sessions_of` uses and
    for its reason: a test may construct a bare application to exercise one route, and an
    `AttributeError` there would reach a caller as a 500 that reads like a bug in the gate
    rather than like an application built without a database.
    """
    found = getattr(request.app.state, "db_sessions", None)
    return found if isinstance(found, async_sessionmaker) else None


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault, identically for every caller.

    A `Failed` rather than an `Absent`, which is `routing_routes._require_sessions`' argument:
    an instance with no pool is broken rather than empty. The difference from that module is
    who reaches this line, and it is the point of
    `A_SECOND_COPY_OF_A_ROW_PREDICATE_IN_FRONT_OF_IT_IS_THE_COPY_THAT_DRIFTS`: here everybody
    does, because the narrowing happens inside the read module and a route that returned early
    for a reader it expected to be refused would make the refused reader the one whose request
    to a broken process succeeded.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


# -------------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["report"])


@router.get("/report/service-levels", response_model=ServiceLevelsView, responses=COMMON_RESPONSES)
async def service_levels(
    request: Request,
    asked: Asked,
    hours: Annotated[int, Query(ge=1, le=MAX_READING_HOURS)] = DEFAULT_READING_HOURS,
) -> ServiceLevelsView:
    """Each lane's measured attainment over the last `hours`, as this reader may be shown it.

    The window ends at the instant the request was admitted rather than at one the caller
    names. A reading is a sum over the whole install, so the only thing a caller could do with
    an arbitrary window is ask for a narrower one, and `brain.console.service_level_view` has
    already decided that a reading is offered whole or not at all: an end instant on the
    request would be a narrowing the read module did not take.

    `service_levels_for_reader` reads the store and then narrows, in that order, and this
    route does not reorder it. See `A_REFUSED_READ_DOES_THE_SAME_WORK_AS_A_PERMITTED_ONE` in
    that module.
    """
    factory = _require_sessions(request)
    start = asked.now - timedelta(hours=hours)
    async with factory() as session:
        levels = await service_levels_for_reader(
            session, asked.reach, start=start, end=asked.now, now=asked.now
        )
    return reading_view_of(levels)


@router.get("/report/spend", response_model=SpendReportView, responses=COMMON_RESPONSES)
async def spend(
    request: Request,
    asked: Asked,
    dimension: Dimension = Dimension.DEPARTMENT,
    since: date | None = None,
    until: date | None = None,
    include_machine: bool = False,
) -> SpendReportView:
    """Spend in one dimension, from the materialised view, over what this reader may see.

    `since` is inclusive and `until` exclusive, both UTC days, which is the view's grain and
    the read module's own vocabulary. A window that ends before it starts is that module's
    refusal rather than a check here, so the two cannot disagree about which windows hold a
    day.

    The default dimension is department, because it is the one dimension every reader's own
    grant is written in and therefore the one whose lines are all keys they could have named
    themselves.

    `include_machine` defaults to false and the answer says which it was, which is
    `MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO` carried to the wire: a
    report that quietly included a nightly sync would answer "what does this cost" with the
    price of a schedule.
    """
    factory = _require_sessions(request)
    async with factory() as session:
        refreshed_at, days = await read_spend_daily(session)
    report = spend_report_from_view(
        days,
        refreshed_at,
        asked.reach,
        dimension,
        now=asked.now,
        since=since,
        until=until,
        include_machine=include_machine,
    )
    return spend_view_of(report, dimension)


@router.get("/report/adoption", response_model=AdoptionPage, responses=COMMON_RESPONSES)
async def adoption(
    request: Request,
    asked: Asked,
    days: Annotated[int, Query(ge=1, le=MAX_ADOPTION_DAYS)] = DEFAULT_ADOPTION_DAYS,
    limit: Annotated[int, Query(ge=1, le=MAX_ADOPTION_LINES)] = DEFAULT_ADOPTION_LINES,
) -> AdoptionPage:
    """How much each department this reader may see asked, over the last `days`.

    Two reads and the order matters: the directory's departments, then the questions. A line
    exists for every department the reader's usage grant admits, zero included, which is what
    makes the presence of a line a fact about the reader's reach rather than about what
    happened. `adoption_for_reader` applies the grant; nothing is filtered here.

    The bound is applied to the lines the read module produced, which are already narrowed, so
    a full page says there are more departments this reader may see and never how many they may
    not. That is the order
    `brain.approval_routes.APPROVALS_ARE_FILTERED_BEFORE_THEY_ARE_BOUNDED` argues for, applied
    to a listing whose filter lives one module away.
    """
    factory = _require_sessions(request)
    start = asked.now - timedelta(days=days)
    async with factory() as session:
        departments = list((await session.execute(live_departments())).scalars().all())
        questions = await asked_between(session, start=start, end=asked.now)
    lines = adoption_for_reader(
        questions,
        departments,
        asked.reach,
        start=start,
        end=asked.now,
        now=asked.now,
    )
    shown = lines[:limit]
    return AdoptionPage(
        items=[adoption_view_of(one) for one in shown],
        next_cursor=None,
        truncated=len(shown) >= limit,
    )


@router.get("/report/usage", response_model=UsageView, responses=COMMON_RESPONSES)
async def usage(
    request: Request,
    asked: Asked,
    days: Annotated[int, Query(ge=1, le=MAX_USAGE_DAYS)] = DEFAULT_USAGE_DAYS,
) -> UsageView:
    """Questions and tokens by person, department, model and agent over the last `days`.

    The same two reads as adoption, in the same order, and for the same reason: the directory's
    departments, then the questions. Then the ledger rows in the window whose tokens were counted
    (M27.7.14). `brain.console.usage_screen.usage_for_reader` chooses the questions once, groups
    them twice, joins the tokens to the questions it chose, decides which axes this reader is
    offered, and names what is not measured. Nothing is filtered, summed or named here.
    """
    factory = _require_sessions(request)
    start = asked.now - timedelta(days=days)
    async with factory() as session:
        departments = list((await session.execute(live_departments())).scalars().all())
        questions = await asked_between(session, start=start, end=asked.now)
        metered = await metered_between(session, start=start, end=asked.now)
    screen = usage_for_reader(
        questions,
        departments,
        asked.reach,
        start=start,
        end=asked.now,
        now=asked.now,
        metered=metered,
    )
    return usage_screen_view_of(screen)


@router.get("/report/questions", response_model=QuestionsView, responses=COMMON_RESPONSES)
async def questions(request: Request, asked: Asked) -> QuestionsView:
    """Whether every question on this install is being answered with nothing connected.

    Read from the tool registry this process holds, through `brain.api_routes.row_readers`, the
    function that builds what the answer lane is given. No database is read: nothing on one
    records how a question ended, which `brain.console.questions_view` argues and the response
    carries.

    A process with no registry is a fault identical for every caller, answered as the answer
    route answers it, and it is checked whoever is asking.
    """
    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        raise Failed("no tool registry on this process")
    screen = questions_for_reader(
        connected=bool(row_readers(registry)), entitlement=asked.reach, now=asked.now
    )
    return questions_view_of(screen)


@router.get("/report/quality", response_model=QualityView, responses=COMMON_RESPONSES)
async def quality(request: Request, asked: Asked) -> QualityView:
    """When the permission canaries last ran and how that run ended, if this reader may know.

    The newest attempt is read whoever is asking, and `brain.console.quality_view` decides
    whether this reader is shown it, last. Whether anything starts the canaries is read off
    `brain.ops.schedule_runner.runner_for`, which is the lookup the worker itself makes before
    it starts a control.
    """
    factory = _require_sessions(request)
    async with factory() as session:
        found = (await session.execute(last_canary_run())).first()
    run = (
        None
        if found is None
        else canary_run_of(started_at=found[0], finished_at=found[1], outcome=found[2])
    )
    screen = quality_for_reader(
        run,
        asked.reach,
        now=asked.now,
        started=runner_for(CANARY_CONTROL).run is not None,
    )
    return quality_view_of(screen)
