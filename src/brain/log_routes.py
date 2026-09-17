"""The Logs screen over HTTP: the application's warnings and errors, searchable and paged, for the
administrator who holds the log.

`brain.ops.log_capture` decides what a kept row may carry and `brain.ops.log_store` writes and reads
it. This module decides who may read, and serves what they may.

**Who may read is a capability of its own, held over everything, at the configuration plane.** The
log is the whole install's: no row belongs to a department, and a row names system vocabulary such
as an entity, a field or a capability, which is configuration a reader might not otherwise hold. So
reading it takes `admin:application_log` in a scope that admits a row with no fields, which a
department-scoped grant does not, and the console's configuration plane over the same scope, through
`brain.console.reads.permitted`. An `admin:` capability rather than a `read:` one because
`brain.gate.admission` already withholds every `admin:` capability from a password-only session and
from a token with no session, and a log is where somebody with a stolen password would look first.
The first administrator is granted it through `brain.identity.first_administrator.ADMINISTRATION`,
and one appointed before it existed is granted it at the next start. See
`THE_LOG_IS_THE_WHOLE_INSTALLS_AND_IS_READ_UNDER_A_SECOND_FACTOR`.

**A reader who may not read is refused, in one sentence that names the screen and nothing in it.**
The Errors screen answers a refused reader with empty lists, for
`brain.console.service_level_view`'s reason, and that works there because the reader can see other
failures beside them. Here an empty page would tell an administrator missing the capability that
nothing has gone wrong, which is the one wrong belief a log screen exists to prevent. The refusal is
decided before any statement is built and does not depend on what the table holds, so it says
nothing about whether there is anything to read. See
`A_REFUSED_READER_IS_TOLD_THE_SCREEN_AND_NOTHING_ABOUT_THE_LOG`.

**A page and never a count.** Newest first, at most `MAX_PAGE` rows, and a cursor when there is
more. The search is literal within event names; a level is one level; the window is at most
`MAX_WINDOW`, which is longer than the rows are kept.

**The page says what it cannot show.** Debug is never kept, info is a sample, the worker's output is
on its own container, and rows are kept for the trace window, and each is a field on the answer so
the sentence leaves the page on the day it stops being true.

Task ids: M27.8.14
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.console.reads import ConsoleRead, Plane, permitted
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.log_capture import MAX_EVENT_CHARS, LogLevel
from brain.ops.log_store import (
    DEFAULT_PAGE,
    MAX_PAGE,
    cursor_of,
    entries,
    fields_of,
    position_of,
)
from brain.ops.retention import TRACE_RETENTION_DAYS
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why reading the log is an administration capability held over everything.
THE_LOG_IS_THE_WHOLE_INSTALLS_AND_IS_READ_UNDER_A_SECOND_FACTOR: Final = (
    "No log row belongs to a department, so a grant scoped to one admits none of them, and a row "
    "names entities, fields and capabilities, which is configuration. Reading it takes "
    "admin:application_log over everything and the console's configuration plane over the same "
    "scope. An admin capability, because admission withholds every one of them from a session "
    "with no second factor, and the log is where somebody holding a stolen password looks for "
    "what went wrong on purpose."
)

#: Why a refused reader is refused rather than shown an empty page.
A_REFUSED_READER_IS_TOLD_THE_SCREEN_AND_NOTHING_ABOUT_THE_LOG: Final = (
    "An empty log reads as an install where nothing went wrong, so an administrator missing the "
    "capability would be told the one false thing this screen exists to correct. The refusal "
    "names the screen, is decided before any statement is built, and is the same whatever the "
    "table holds, so it discloses nothing about the log."
)

# ------------------------------------------------------------------------ the figures
#: Reads the application log. Held over everything or not at all.
LOG_AUTHORITY: Final = Capability(value="admin:application_log")

#: The screen's word in a refusal.
LOG_SCREEN: Final = "logs"

#: The read, as `brain.console.reads.permitted` asks it: the authority at the configuration plane.
LOG_READ: Final = ConsoleRead(
    screen=LOG_SCREEN,
    tool="console.application_log",
    requires=LOG_AUTHORITY,
    plane=Plane.CONFIGURATION,
)

#: The window when nobody says, and the longest one may ask for.
DEFAULT_WINDOW: Final = timedelta(days=1)
MAX_WINDOW: Final = timedelta(days=TRACE_RETENTION_DAYS + 1)


# ------------------------------------------------------------------------ the shapes
class LogEntryView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    #: When the last repeat folded into this row was made.
    last_at: datetime
    level: LogLevel
    #: The event name, or null when it was not written literally in the source.
    event: str | None
    #: `module:line` of the call.
    origin: str | None
    #: The trace reference a person is shown beside a failure, when one was bound.
    reference: str | None
    #: The exception's type, never its message.
    error_type: str | None
    repeats: int
    #: Names to short values, each kept in the clear or as its shape, never a value otherwise.
    fields: dict[str, str]


class LogPage(BaseModel):
    """Kept log rows in a window, newest first, as asked. No count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    entries: list[LogEntryView]
    #: Where the next page starts, or null when this page holds the last row.
    next_cursor: str | None
    #: How long a row is kept once the retention sweep is released.
    kept_for_days: int = TRACE_RETENTION_DAYS
    #: Debug calls are never kept.
    debug_is_not_kept: bool = True
    #: Info calls are kept as a bounded sample.
    info_is_a_sample: bool = True
    #: The background worker prints to its own container's output, which is not kept here.
    worker_output_is_not_kept: bool = True


# ---------------------------------------------------------------- the decision
def may_read_application_log(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read the log: the authority and its plane, over the whole install.

    See `THE_LOG_IS_THE_WHOLE_INSTALLS_AND_IS_READ_UNDER_A_SECOND_FACTOR`.
    """
    return permitted(LOG_READ, reach, now) and _in_reach(reach, LOG_AUTHORITY, NOWHERE, now)


# ------------------------------------------------------------------------ the wiring
def _refused_input(field: str, message: str) -> RequestValidationError:
    """A malformed parameter, as the 422 every other malformed parameter gets."""
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", field), "msg": message, "input": None}]
    )


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def window_of(
    start: datetime | None, end: datetime | None, now: datetime
) -> tuple[datetime, datetime]:
    """The window asked for, defaulted, or a 422 for one that is naive, inverted or too long."""
    for name, value in (("start", start), ("end", end)):
        if value is not None and value.tzinfo is None:
            raise _refused_input(name, "an instant without an offset is not an instant")
    until = end if end is not None else now
    since = start if start is not None else until - DEFAULT_WINDOW
    if since >= until:
        raise _refused_input("start", "the window starts after it ends")
    if until - since > MAX_WINDOW:
        raise _refused_input("start", f"a window is at most {MAX_WINDOW.days} days")
    return since, until


router = APIRouter(prefix=API_PREFIX, tags=["operate"])


@router.get("/logs", response_model=LogPage, responses=COMMON_RESPONSES)
async def logs(
    request: Request,
    asked: Asked,
    level: LogLevel | None = None,
    event: Annotated[str | None, Query(min_length=1, max_length=MAX_EVENT_CHARS)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> LogPage:
    """One page of the kept log, newest first, narrowed by level, event name and window.

    The decision first, then the parameters, then the database. See
    `A_REFUSED_READER_IS_TOLD_THE_SCREEN_AND_NOTHING_ABOUT_THE_LOG`.
    """
    if not may_read_application_log(asked.reach, asked.now):
        raise Absent(f"the {LOG_SCREEN} screen is not answerable for this caller")
    since, until = window_of(start, end, asked.now)
    after = None
    if cursor is not None:
        try:
            after = position_of(cursor)
        except ValueError:
            raise _refused_input("cursor", "malformed cursor") from None
    statement = entries(start=since, end=until, level=level, event=event, after=after, limit=limit)
    async with _require_sessions(request)() as session:
        found = (await session.execute(statement)).all()
    page = found[:limit]
    return LogPage(
        start=since,
        end=until,
        entries=[
            LogEntryView(
                at=at,
                last_at=last_at,
                level=LogLevel(stored_level),
                event=stored_event,
                origin=origin,
                reference=trace_id,
                error_type=error_type,
                repeats=repeats,
                fields=dict(fields_of(stored_fields)),
            )
            for (
                _,
                at,
                last_at,
                stored_level,
                stored_event,
                origin,
                trace_id,
                error_type,
                repeats,
                stored_fields,
            ) in page
        ],
        next_cursor=cursor_of(page[-1][1], page[-1][0]) if len(found) > limit else None,
    )
