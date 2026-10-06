"""The audit screen's refusal and redaction statistics over HTTP, counted in the reader's own view.

`brain.console.auditor.refusal_statistics` and `redaction_statistics` were written and argued, and
nothing reached them: no route served them and the Activity screen drew neither. This module is the
read they sit behind, and it decides nothing about what a reader may see. Every entry counted came
out of `brain.audit.view.AuditView`, built over the window this module loaded and judged at the
reader's own reach, and every shape counted came through `brain.console.auditor.shapes_told`, which
asks `brain.ops.denial_alerts.reach` whether the reader would have been told it.

**The audit screen's read first, before the ledger is touched**, with `brain.audit_routes`' one
refusal in its words, so a reader with no grant is answered alike on a process with a ledger and on
one without, and alike on this address and on the ledger's own.

**Two counts and nothing beside them that could be subtracted.** The refusals, by the shape
`denial_alerts` assessed and its own sentence, and the number of entries that carried a redaction.
No capability, field, object or person, and no total of the window: see
`brain.console.auditor.A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS` and
`NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE`. **Neither counts the reader's own entries**, which is
`A_READER_IS_NEVER_COUNTED_WHAT_WAS_KEPT_FROM_THEM` and is decided in the auditor module rather
than here, so the rule cannot be bypassed by a second route.

**The patterns are the digest's own.** `brain.ops.denial_digest_run.denials_between` groups the
window's `deny` entries per person and capability and `patterns_from` assesses them through
`limits.assess_denials`, the statement and the classifier the hourly alert pass runs. Rejected:
assessing the reader's visible denials here, which would be this route forming the opinion
`refusal_statistics` says only `denial_alerts` may hold, and would give two answers to what a run of
refusals looks like.

**Reading stops at a ceiling and the ceiling is stated, never measured.** The window is read newest
first in `brain.audit_routes.LOAD_CHUNK` rows to `READ_CEILING`, and the answer carries that
ceiling as a constant, the same for every reader and every window. A flag saying the load came back
full would say the ledger holds at least that many entries in the window, readable or not, which is
a count of hidden entries arrived at by a boolean; `brain.estate_routes` makes the same decision
about the memory viewer. See `THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT`.

**The window is the last seven days unless asked**, the Audit screen's own opening period, and is
held to `AuditFilter`'s rules: an aware instant and an ordered range, refused as the 422 any
malformed parameter is, identically whatever the ledger holds.

Task ids: M33.4.1.3
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.audit.ledger import AuditEntry
from brain.audit.view import MAX_PAGE_SIZE, AuditFilter, AuditRow, AuditView
from brain.audit_routes import AUDIT_SCREEN, LOAD_CHUNK, READ_CEILING, entry_from, ledger_of
from brain.console.auditor import redaction_statistics, refusal_statistics, shapes_told
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.ops.denial_alerts import DenialPattern
from brain.ops.denial_digest_run import denials_between, patterns_from
from brain.routing_routes import sessions_of

log = structlog.get_logger()

STATISTICS_PATH: Final = "/audit/statistics"

#: The window the statistics cover when none is asked for: the Audit screen's opening period.
DEFAULT_WINDOW: Final = timedelta(days=7)

#: Why the answer states the reading ceiling rather than saying whether it was reached.
THE_CEILING_IS_A_CONSTANT_AND_NOT_A_MEASUREMENT: Final = (
    "The window is read up to a ceiling of ledger entries, readable or not. Saying whether the "
    "ceiling was reached would say the ledger holds at least that many entries in the window, "
    "which counts entries the reader may not see. So the ceiling is sent as a constant, the same "
    "for every reader and every window, and nothing on the answer varies with how much was read."
)


class RefusalShapeView(BaseModel):
    """One shape of refusal, `denial_alerts`' sentence for it, and how often it happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: str
    reads_as: str
    occurrences: int


class AuditStatisticsView(BaseModel):
    """Refusals by shape and entries carrying a redaction, over other people's entries this
    reader may read in the window. No capability, field, object, person or total."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    since: datetime
    until: datetime
    refusals: list[RefusalShapeView]
    redacted_entries: int
    #: The most ledger entries one answer is counted over, newest first. A constant.
    read_at_most: int


@runtime_checkable
class DenialPatterns(Protocol):
    """Where the window's assessed runs of refusals come from: `StoredDenialPatterns`."""

    async def between(self, since: datetime, until: datetime) -> tuple[DenialPattern, ...]:
        """The patterns worth an alert among the `deny` entries in `[since, until)`."""
        ...


class StoredDenialPatterns:
    """The digest's grouped statement and classifier, over the window asked rather than the hour."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def between(self, since: datetime, until: datetime) -> tuple[DenialPattern, ...]:
        async with self._sessions() as session, session.begin():
            found = await session.execute(denials_between(since, until))
            return patterns_from([row._tuple() for row in found.all()])


def patterns_of(request: Request) -> DenialPatterns:
    """`app.state.denial_patterns` when something put one there, the database otherwise.

    `brain.audit_routes.ledger_of`'s arrangement, so an application built without a database can
    still be given patterns to count.
    """
    found = getattr(request.app.state, "denial_patterns", None)
    if isinstance(found, DenialPatterns):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredDenialPatterns(factory)


def _not_answerable() -> Absent:
    """`brain.audit_routes`' one refusal, in its words. Names the screen and nothing else."""
    return Absent(f"the {AUDIT_SCREEN} screen is not answerable for this caller")


def _refused_window(message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", "window"), "msg": message, "input": None}]
    )


def visible_rows(view: AuditView) -> tuple[AuditRow, ...]:
    """Every row of the view, a page at a time. The view decided each one."""
    rows: list[AuditRow] = []
    cursor: str | None = None
    while True:
        page = view.page(limit=MAX_PAGE_SIZE, cursor=cursor, newest_first=True)
        rows.extend(page.rows)
        if page.next_cursor is None:
            return tuple(rows)
        cursor = page.next_cursor


router = APIRouter(prefix=API_PREFIX, tags=["audit"])


@router.get(STATISTICS_PATH, response_model=AuditStatisticsView, responses=COMMON_RESPONSES)
async def audit_statistics(
    request: Request,
    asked: Asked,
    since: datetime | None = None,
    until: datetime | None = None,
) -> AuditStatisticsView:
    """Refusals by shape and redacted entries, over other people's entries this reader may read.

    The screen's question first, then the window, then the ledger. See the module docstring.
    """
    if not permitted(screen(AUDIT_SCREEN).read, asked.reach, asked.now):
        log.info("audit statistics not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    ends = until if until is not None else asked.now
    starts = since if since is not None else ends - DEFAULT_WINDOW
    try:
        window = AuditFilter(since=starts, until=ends)
    except ValidationError as refused:
        raise _refused_window(str(refused.errors()[0]["msg"])) from None

    ledger = ledger_of(request)
    loaded: list[AuditEntry] = []
    position: tuple[datetime, str] | None = None
    read = 0
    while read < READ_CEILING:
        rows = await ledger.window(window, position=position, newest_first=True, limit=LOAD_CHUNK)
        read += len(rows)
        loaded.extend(entry for entry in (entry_from(row) for row in rows) if entry is not None)
        if len(rows) < LOAD_CHUNK:
            break
        position = (rows[-1].at, rows[-1].entry_hash)

    view = AuditView(loaded, reader=asked.reach, now=asked.now)
    patterns = await patterns_of(request).between(starts, ends)
    reader_id = asked.reach.principal_id
    refusals = refusal_statistics(
        view, shapes=shapes_told(patterns, asked.reach, now=asked.now), reader_id=reader_id
    )
    return AuditStatisticsView(
        since=starts,
        until=ends,
        refusals=[
            RefusalShapeView(
                shape=one.shape.value, reads_as=one.reads_as, occurrences=one.occurrences
            )
            for one in refusals
        ],
        redacted_entries=redaction_statistics(visible_rows(view), reader_id=reader_id),
        read_at_most=READ_CEILING,
    )
