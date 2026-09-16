"""The Errors screen over HTTP: the failures this install keeps a durable record of, and what it
keeps no record of at all.

`docs/admin-console.md` asks for logs and errors readable without a shell on the server. What the
application does with its log decides how much of that can be true, and it is less than the
sentence asks. **Nothing configures structlog, so every log line is text on the container's
standard output, and nothing keeps a copy anywhere the application can read.** A console screen
of the process log would need a log store, and a log store needs a redactor on its way in:
several call sites log `str(exc)`, which quotes whatever the exception quoted, and nothing strips
values from a log line before it is written. Building one is a task with its own argument, and
this module does not pretend it has been done. See
`THE_PROCESS_LOG_IS_KEPT_BY_THE_CONTAINER_AND_NOT_BY_THE_APPLICATION`.

**What is served is the two failure records the database already keeps, each behind the decision
that already says who may see it.**

- A scheduled job that failed: `ops.control_run` with outcome `failed`. Who may see a job is
  `brain.jobs_routes.may_see_job`, the Live runs decision for what is owed, and the jobs a reader
  may see are chosen before the query so the bound on the list is a bound on rows they may see.
  The failure is shown as its type and never its message; see
  `brain.jobs_routes.AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE`.
- A request that failed or degraded: `obs.request_telemetry` with status `failed` or `degraded`.
  Its reference, when it arrived, its lane, how it ended and how long it took, and nothing that
  names a person: no principal, no entitlement hash, and no question, which the row does not
  hold. A request is everybody's traffic, so a reader is shown these exactly when the Service
  levels screen would show them the whole install's reading, which is
  `brain.console.service_level_view.may_read_service_levels` behind that screen's `permitted`.
  The reference is the one the console shows a person beside a failure, so an administrator
  told a reference can find what happened to it.

**A list and never a count, and a full list says so.** Each list is bounded, newest first, and
`truncated` says a list came back full. Because the bound applies only to rows the reader may
see, a full list says nothing about rows they may not.

**Not claimed: M27.8.14.** Errors are readable; the log is not, and the leaf names both.

Task ids: none
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.service_level_view import SCREEN_KEY, may_read_service_levels
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.jobs_routes import failure_kind, may_see_job
from brain.ops.controls import CONTROLS
from brain.ops.telemetry import RequestStatus
from brain.report_routes import MAX_READING_HOURS
from brain.routing_routes import sessions_of
from brain.tables.schedule import ControlRunRow
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the process log is not on this screen.
THE_PROCESS_LOG_IS_KEPT_BY_THE_CONTAINER_AND_NOT_BY_THE_APPLICATION: Final = (
    "The application writes its log as text to its container's standard output and keeps no "
    "copy, so a console cannot read it without a log store. A log store is not a table and a "
    "select: several call sites log an exception's text, which can quote a value, and nothing "
    "removes values from a log line before it is written. Serving the log without that would put "
    "whatever an exception quoted on a screen, so the screen serves the failures the database "
    "keeps and says where the log is."
)

# ------------------------------------------------------------------------ the figures
#: How many failures of each kind one answer carries at most. A resource bound on the page.
MAX_FAILURES: Final = 200

#: The window when nobody says, and the longest one may ask for: the Service levels bound.
DEFAULT_WINDOW_HOURS: Final = 24 * 7
MAX_WINDOW_HOURS: Final = MAX_READING_HOURS

#: The request outcomes that are a failure somebody would ask about.
FAILED_REQUESTS: Final[tuple[str, ...]] = (
    RequestStatus.FAILED.value,
    RequestStatus.DEGRADED.value,
)


# ------------------------------------------------------------------------ the shapes
class JobFailureView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    started_at: datetime
    finished_at: datetime | None
    #: The exception's type, or null when the record does not start with one. Never its message.
    kind: str | None


class RequestFailureView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The reference a person is shown beside a failure.
    reference: str
    received_at: datetime
    lane: str
    status: str
    duration_ms: float


class ErrorsPage(BaseModel):
    """Failures in a window, newest first, as this reader may see them. No count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    jobs: list[JobFailureView]
    jobs_truncated: bool
    requests: list[RequestFailureView]
    requests_truncated: bool
    #: The process log is on the container's standard output and nowhere the console can read.
    process_log_is_not_kept: bool = True
    #: A failed job's message stays in its run record on the server.
    failure_messages_stay_on_the_server: bool = True


# ---------------------------------------------------------------- the statements
def failed_runs(
    names: tuple[str, ...], start: datetime, end: datetime
) -> Select[tuple[str, datetime, datetime | None, str | None]]:
    """Failed runs of these controls that started in `[start, end)`, newest first, one past the
    bound so a full list can say so."""
    return (
        select(
            ControlRunRow.name,
            ControlRunRow.started_at,
            ControlRunRow.finished_at,
            ControlRunRow.detail,
        )
        .where(
            ControlRunRow.outcome == "failed",
            ControlRunRow.name.in_(names),
            ControlRunRow.started_at >= start,
            ControlRunRow.started_at < end,
        )
        .order_by(ControlRunRow.started_at.desc())
        .limit(MAX_FAILURES + 1)
    )


def failed_requests(
    start: datetime, end: datetime
) -> Select[tuple[str, datetime, str, str, float]]:
    """Failed and degraded requests that arrived in `[start, end)`, newest first. Five columns
    and none of them names a person."""
    return (
        select(
            RequestTelemetryRow.trace_id,
            RequestTelemetryRow.received_at,
            RequestTelemetryRow.lane,
            RequestTelemetryRow.status,
            RequestTelemetryRow.duration_ms,
        )
        .where(
            RequestTelemetryRow.status.in_(FAILED_REQUESTS),
            RequestTelemetryRow.received_at >= start,
            RequestTelemetryRow.received_at < end,
        )
        .order_by(RequestTelemetryRow.received_at.desc())
        .limit(MAX_FAILURES + 1)
    )


# ---------------------------------------------------------------- the decisions
def visible_jobs(reach: EntitlementSet, now: datetime) -> tuple[str, ...]:
    """Every control whose failures this reach may see, by the Jobs screen's decision."""
    return tuple(one.name for one in CONTROLS if may_see_job(one.name, reach, now))


def may_see_request_failures(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may see individual failed requests: exactly when the Service levels
    screen would show it the whole install's reading."""
    return permitted(screen(SCREEN_KEY).read, reach, now) and may_read_service_levels(
        reach, now=now
    )


# ------------------------------------------------------------------------ the wiring
def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


router = APIRouter(prefix=API_PREFIX, tags=["operate"])


@router.get("/errors", response_model=ErrorsPage, responses=COMMON_RESPONSES)
async def errors(
    request: Request,
    asked: Asked,
    hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = DEFAULT_WINDOW_HOURS,
) -> ErrorsPage:
    """Failed jobs and failed requests in the last `hours`, as this reader may see them.

    Both statements are made whoever asks, and the narrowing decides what they return rather than
    whether they run, for `brain.console.service_level_view`'s reason: a refused reader whose
    request did less work would be told so by the time it took.
    """
    start = asked.now - timedelta(hours=hours)
    names = visible_jobs(asked.reach, asked.now)
    requests_visible = may_see_request_failures(asked.reach, asked.now)
    async with _require_sessions(request)() as session:
        runs = (await session.execute(failed_runs(names, start, asked.now))).all()
        found = (await session.execute(failed_requests(start, asked.now))).all()
    if not requests_visible:
        found = []
    return ErrorsPage(
        start=start,
        end=asked.now,
        jobs=[
            JobFailureView(
                control=name, started_at=started, finished_at=finished, kind=failure_kind(detail)
            )
            for name, started, finished, detail in runs[:MAX_FAILURES]
        ],
        jobs_truncated=len(runs) > MAX_FAILURES,
        requests=[
            RequestFailureView(
                reference=trace_id,
                received_at=received,
                lane=lane,
                status=status,
                duration_ms=duration,
            )
            for trace_id, received, lane, status, duration in found[:MAX_FAILURES]
        ],
        requests_truncated=len(found) > MAX_FAILURES,
    )
