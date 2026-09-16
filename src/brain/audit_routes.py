"""The audit ledger over HTTP: one reader's view of it, narrowed without naming what is withheld.

`brain.audit.view.AuditView` decides entry by entry what a reader may see of `obs.audit_entry`,
and `brain.console.auditor.permission_history` narrows that to what changed one subject's reach.
Neither was reachable from a browser, and nothing in the application had ever read the table:
every entry the grant, sign-in and session triggers append was written for an auditor who had no
screen. `brain.ops.console_screens` counted `brain.console.auditor` among the reads with no
screen, and the design's Govern section names an Audit item the console did not have. This
module is the read those two decisions sit behind (M27.7.13).

**Nothing here decides who may see an entry.** Every row on every answer came out of
`AuditView.page`, which applies `_may_see` to each entry and fills a page from what survives, and
the history came out of `permission_history`, which is a narrowing of the same page. A route that
dropped an entry itself would be a second answer to the view's question, and the permissive copy is
the one that ships. The screen opens on `brain.console.reads.permitted` over the Audit screen's
own read, before the database is looked at, for `brain.govern_routes`' reason: a caller with no
grant is refused identically on a process with a ledger and on one without.

**The filters are the view's filters and are applied twice, once to load less.** Action, subject
kind, actor and a date range, which is `AuditFilter` exactly, with no free text and no substring,
for the reason that model gives about a search box over a permission map. The same filter is put
into the statement so a window of a busy ledger is not read to find three entries, and handed to
the view, whose application is the one that counts: the statement's copy can only load fewer rows
than the view would have admitted, never more. See `A_FILTER_IN_THE_STATEMENT_ONLY_LOADS_LESS`.

**A filter offers no value the reader has not been shown.** The action and subject-kind lists are
the product's closed vocabularies, identical in every install and in the source, so offering them
says nothing about this company's ledger. The people a reader may narrow to are the actors on the
rows they were just shown, and nothing else: a list of actors assembled from the table would be a
list of who has done anything here, handed to a reader whose rows were carefully withheld. See
`A_FILTER_OFFERS_THE_VOCABULARY_AND_THE_ROWS_ALREADY_SHOWN`.

**No count, total or residual anywhere, and the answer model has nowhere to put one.**
`AuditPage` has no total for the reason it gives, and `AuditLedgerPage` here is a new model rather
than `brain.api.Page`, because that model carries an optional `total` and this one must not be one
edit away from populating it. `extra="forbid"` holds the line.

**Reading stops at a ceiling, and the cursor says where rather than how much.** A page is filled
from the entries the reader may see, so finding fifty of them may mean reading far more than fifty
rows. The route reads the window in chunks until the page is full, the window is exhausted, or
`READ_CEILING` rows have been read, and in the last case it returns what it found with a cursor
past the last row read. The next page carries on from there. That is a short page with a cursor,
which says the ledger is long, and never a number: the alternative, reading without a ceiling, is
a request that loads the ledger into memory for a reader who may see none of it. See
`A_READING_CEILING_SAYS_WHERE_IT_STOPPED_AND_NEVER_HOW_MUCH_IT_PASSED`.

**Newest first by default, oldest first on request.** An auditor opening the screen asks what just
happened; one reconstructing an incident reads forwards. `AuditView.page` walks either way over the
same visible entries.

**A row that does not construct as an `AuditEntry` is skipped and logged, never shown and never
repaired.** The type refuses a detail the redactor would have stripped, so a row written by hand
carrying a value is exactly the row that must not reach a screen, and a page that raised on it would
take the ledger away from every reader over one bad row.

**What has never run.** This repository's development machine has no PostgreSQL, so the window
statement has not been executed against one here. What is tested is the statement it compiles to,
every refusal, the order the checks happen in, and the whole route over a store holding real
entries appended by `AuditChain`.

Task ids: M27.7.13
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated, Any, Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Select, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.audit.ledger import IDENTIFIER, SUBJECT_KINDS, AuditAction, AuditEntry
from brain.audit.view import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    AuditFilter,
    AuditPage,
    AuditRow,
    AuditView,
    cursor_after,
    position_of,
)
from brain.console.auditor import PERMISSION_ACTIONS, permission_history
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.routing_routes import sessions_of
from brain.tables.audit import AuditEntryRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the filter is put into the statement as well as handed to the view.
A_FILTER_IN_THE_STATEMENT_ONLY_LOADS_LESS: Final = (
    "AuditFilter matches an entry on its action, its subject kind, its actor and its instant, "
    "all columns of obs.audit_entry, so the same filter can be put into the statement that loads "
    "a window. That copy is not a decision: it can only leave out rows the view's own filter "
    "would have left out, and the view applies the filter again to what was loaded. Without it a "
    "reader narrowing a busy ledger to one action reads every other action to find it."
)

#: Why the filter lists offer what they offer.
A_FILTER_OFFERS_THE_VOCABULARY_AND_THE_ROWS_ALREADY_SHOWN: Final = (
    "An action and a subject kind are words from the product's closed vocabulary, in the source "
    "and the same in every install, so offering all of them tells a reader nothing about this "
    "company. A person is different: the actors offered are the actors on the rows this reader "
    "was just shown and no others, because a list of actors read from the table is a list of "
    "everybody who has done anything here, handed to a reader whose rows were withheld."
)

#: Why a page may stop short with a cursor.
A_READING_CEILING_SAYS_WHERE_IT_STOPPED_AND_NEVER_HOW_MUCH_IT_PASSED: Final = (
    "A page is filled from the entries a reader may see, so filling it can mean reading many "
    "more rows than it shows. Reading stops at a ceiling, and the page then carries what it "
    "found and a cursor past the last row read, so the next page continues from there and "
    "nothing the reader may see is skipped. A short page with a cursor says the ledger is long; "
    "it carries no number, and the alternative is a request that reads the whole ledger into "
    "memory for a reader who may be shown none of it."
)

# ----------------------------------------------------------------- the screen

#: The screen whose read decides whether this ledger opens at all.
AUDIT_SCREEN: Final = "audit"

#: How many rows one statement loads. A resource bound, not a permission one.
LOAD_CHUNK: Final = 500

#: The most rows one request reads before it returns what it found. See
#: `A_READING_CEILING_SAYS_WHERE_IT_STOPPED_AND_NEVER_HOW_MUCH_IT_PASSED`.
READ_CEILING: Final = 5000


class Order(enum.StrEnum):
    """Which way a page walks the ledger."""

    NEWEST = "newest"
    OLDEST = "oldest"


# ------------------------------------------------------------------- the shapes


class AuditRowView(BaseModel):
    """One entry as a person reads it. `AuditRow`'s fields, and nothing a chain position is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    action: AuditAction
    actor_id: str
    subject_kind: str
    subject_id: str
    details: dict[str, str]


class AuditLedgerPage(BaseModel):
    """One page of the ledger, where to continue, and what a filter may offer.

    Not `brain.api.Page`: see the module docstring on why this answer has no field a total could
    be written into.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AuditRowView]
    next_cursor: str | None
    order: Order
    #: The product's closed vocabularies. See
    #: `A_FILTER_OFFERS_THE_VOCABULARY_AND_THE_ROWS_ALREADY_SHOWN`.
    actions: list[AuditAction]
    subject_kinds: list[str]
    #: The actors on the rows above, in the order they first appear, and no others.
    actors: list[str]


class PermissionEventView(BaseModel):
    """One change to what a subject may do, as the history lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    action: AuditAction
    actor_id: str
    details: dict[str, str]


class PermissionHistoryView(BaseModel):
    """Everything this reader may see that changed one subject's reach, oldest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_kind: str
    subject_id: str
    events: list[PermissionEventView]
    #: The history filled a whole page of what this reader may see. A fact about their own view.
    full: bool


# ---------------------------------------------------------------- the statements


def _ordered_hash() -> Any:
    """The digest under the byte collation, so the database orders ties as Python does."""
    return AuditEntryRow.entry_hash.collate("C")


def window(
    criteria: AuditFilter,
    *,
    subject: str | None = None,
    position: tuple[datetime, str] | None,
    newest_first: bool,
    limit: int,
) -> Select[tuple[AuditEntryRow]]:
    """The next `limit` rows past `position` in the walking direction, narrowed by `criteria`.

    See `A_FILTER_IN_THE_STATEMENT_ONLY_LOADS_LESS`. The subject kind is matched as the prefix
    `<kind>:` with the colon, so `principal` does not match a kind that merely begins with it, and
    the kinds are a closed vocabulary with no wildcard characters in them. Ordered and compared on
    `(at, entry_hash)` in that collation, which is `AuditView`'s own order.

    `subject` is one exact `<kind>:<id>`, for the permission history, which narrows its input to
    one subject rather than reading every entry of that kind to find them.
    """
    query = select(AuditEntryRow)
    if subject is not None:
        query = query.where(AuditEntryRow.subject == subject)
    if criteria.actions:
        query = query.where(AuditEntryRow.action.in_(sorted(a.value for a in criteria.actions)))
    if criteria.subject_kinds:
        query = query.where(
            or_(
                *(
                    AuditEntryRow.subject.startswith(f"{kind}:", autoescape=True)
                    for kind in sorted(criteria.subject_kinds)
                )
            )
        )
    if criteria.actors:
        query = query.where(AuditEntryRow.actor_id.in_(sorted(criteria.actors)))
    if criteria.since is not None:
        query = query.where(AuditEntryRow.at >= criteria.since)
    if criteria.until is not None:
        query = query.where(AuditEntryRow.at < criteria.until)
    if position is not None:
        here = tuple_(AuditEntryRow.at, _ordered_hash())
        there = tuple_(literal(position[0]), literal(position[1]))
        query = query.where(here < there if newest_first else here > there)
    if newest_first:
        query = query.order_by(AuditEntryRow.at.desc(), _ordered_hash().desc())
    else:
        query = query.order_by(AuditEntryRow.at, _ordered_hash())
    return query.limit(limit)


def entry_from(row: AuditEntryRow) -> AuditEntry | None:
    """One stored row as the entry the view decides over, or None and a log line.

    See the module docstring on a row that does not construct. The log names the sequence number
    and never a detail, because the detail is the thing that failed to be a name.
    """
    try:
        return AuditEntry(
            seq=row.seq,
            at=row.at,
            actor_id=row.actor_id,
            action=AuditAction(row.action),
            subject=row.subject,
            ent_hash=row.ent_hash,
            trace_id=row.trace_id,
            details=dict(row.details),
            prev_hash=row.prev_hash,
            entry_hash=row.entry_hash,
        )
    except (ValueError, ValidationError):
        log.warning("audit entry does not construct", seq=row.seq)
        return None


# ------------------------------------------------------------------- the store


@runtime_checkable
class LedgerWindows(Protocol):
    """Where windows of the ledger are read from. `StoredLedger` over a database."""

    async def window(
        self,
        criteria: AuditFilter,
        *,
        subject: str | None = None,
        position: tuple[datetime, str] | None,
        newest_first: bool,
        limit: int,
    ) -> Sequence[AuditEntryRow]:
        """The rows `window` selects."""
        ...


class StoredLedger:
    """`obs.audit_entry`, read as the application role. Its policy admits every row to read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def window(
        self,
        criteria: AuditFilter,
        *,
        subject: str | None = None,
        position: tuple[datetime, str] | None,
        newest_first: bool,
        limit: int,
    ) -> Sequence[AuditEntryRow]:
        statement = window(
            criteria, subject=subject, position=position, newest_first=newest_first, limit=limit
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalars().all()


def ledger_of(request: Request) -> LedgerWindows:
    """The ledger this process reads, or one fault identical for every caller.

    `app.state.audit_ledger` when something put one there, and the database otherwise, which is
    `brain.govern_routes._require_console_reads`' arrangement: nothing in `brain.app` sets it, and
    an application built without a database can still be given a ledger to read.
    """
    found = getattr(request.app.state, "audit_ledger", None)
    if isinstance(found, LedgerWindows):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredLedger(factory)


# ---------------------------------------------------------------- the reading


async def read_page(
    ledger: LedgerWindows,
    view_of: Callable[[Sequence[AuditEntry]], AuditView],
    criteria: AuditFilter,
    *,
    limit: int,
    cursor: str | None,
    newest_first: bool,
) -> AuditPage:
    """One page of what this reader may see, read in chunks up to `READ_CEILING`.

    `view_of` builds the `AuditView` over what has been loaded so far, so the reader and the
    instant are bound once by the caller. The page is recomputed over everything loaded after each
    chunk rather than stitched from per-chunk pages, so its rows and its cursor are exactly
    `AuditView.page`'s over one sequence. See
    `A_READING_CEILING_SAYS_WHERE_IT_STOPPED_AND_NEVER_HOW_MUCH_IT_PASSED` for the last branch.
    """
    position = position_of(cursor) if cursor is not None else None
    loaded: list[AuditEntry] = []
    read = 0
    while True:
        rows = await ledger.window(
            criteria, position=position, newest_first=newest_first, limit=LOAD_CHUNK
        )
        read += len(rows)
        loaded.extend(entry for entry in (entry_from(row) for row in rows) if entry is not None)
        if rows:
            position = (rows[-1].at, rows[-1].entry_hash)
        page = view_of(loaded).page(criteria, limit=limit, cursor=cursor, newest_first=newest_first)
        if page.next_cursor is not None or len(rows) < LOAD_CHUNK:
            return page
        if read >= READ_CEILING:
            continuing = cursor_after(loaded[-1]) if loaded else None
            return AuditPage(rows=page.rows, next_cursor=continuing)


def _refused_input(field: str, message: str) -> RequestValidationError:
    """A filter or cursor the view refuses, as the 422 every other malformed parameter gets.

    Raised identically whatever the ledger holds, because every check behind it is a pure function
    of the parameters.
    """
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", field), "msg": message, "input": None}]
    )


def _not_answerable() -> Absent:
    """The one refusal this router makes. Names the screen, never an entry or the caller."""
    return Absent(f"the {AUDIT_SCREEN} screen is not answerable for this caller")


def row_view(row: AuditRow) -> AuditRowView:
    return AuditRowView(
        at=row.at,
        action=row.action,
        actor_id=row.actor_id,
        subject_kind=row.subject_kind,
        subject_id=row.subject_id,
        details=dict(row.details),
    )


def actors_on(rows: Sequence[AuditRow]) -> list[str]:
    """The actors on these rows, first appearance first, each once. Never read from the table."""
    seen: dict[str, None] = {}
    for row in rows:
        seen.setdefault(row.actor_id, None)
    return list(seen)


router = APIRouter(prefix=API_PREFIX, tags=["audit"])


@router.get("/audit", response_model=AuditLedgerPage, responses=COMMON_RESPONSES)
async def audit_page(
    request: Request,
    asked: Asked,
    action: AuditAction | None = None,
    subject_kind: Annotated[str | None, Query(max_length=32)] = None,
    actor: Annotated[str | None, Query(pattern=IDENTIFIER)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    order: Order = Order.NEWEST,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> AuditLedgerPage:
    """One page of the ledger this reader may see, narrowed by exact filters.

    The screen's question first, then the filter the view would refuse, then the database. A
    subject kind outside `SUBJECT_KINDS`, a naive or inverted date range and a malformed cursor
    are the 422 a malformed parameter always is.
    """
    if not permitted(screen(AUDIT_SCREEN).read, asked.reach, asked.now):
        log.info("audit screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    try:
        criteria = AuditFilter(
            actions=frozenset({action}) if action is not None else frozenset(),
            subject_kinds=frozenset({subject_kind}) if subject_kind is not None else frozenset(),
            actors=frozenset({actor}) if actor is not None else frozenset(),
            since=since,
            until=until,
        )
    except ValidationError as refused:
        raise _refused_input("filter", str(refused.errors()[0]["msg"])) from None
    if cursor is not None:
        try:
            position_of(cursor)
        except ValueError:
            raise _refused_input("cursor", "malformed cursor") from None

    ledger = ledger_of(request)
    newest_first = order is Order.NEWEST
    page = await read_page(
        ledger,
        lambda loaded: AuditView(loaded, reader=asked.reach, now=asked.now),
        criteria,
        limit=limit,
        cursor=cursor,
        newest_first=newest_first,
    )
    return AuditLedgerPage(
        items=[row_view(row) for row in page.rows],
        next_cursor=page.next_cursor,
        order=order,
        actions=list(AuditAction),
        subject_kinds=sorted(SUBJECT_KINDS),
        actors=actors_on(page.rows),
    )


@router.get("/audit/history", response_model=PermissionHistoryView, responses=COMMON_RESPONSES)
async def audit_history(
    request: Request,
    asked: Asked,
    subject_kind: Annotated[str, Query(max_length=32)],
    subject_id: Annotated[str, Query(pattern=IDENTIFIER)],
) -> PermissionHistoryView:
    """Everything this reader may see that changed what one subject may do, oldest first.

    `brain.console.auditor.permission_history` is the narrowing and the view inside it is the
    decision. The window is loaded already narrowed to the four permission actions and to this
    subject's own entries, so the history's page is filled from them rather than from every
    entry of that kind; that is the input narrowed, which `brain.member_activity` argues is the
    only safe place to narrow a view.
    """
    if not permitted(screen(AUDIT_SCREEN).read, asked.reach, asked.now):
        log.info("audit screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    if subject_kind not in SUBJECT_KINDS:
        raise _refused_input("subject_kind", "not a subject kind")

    ledger = ledger_of(request)
    criteria = AuditFilter(
        actions=frozenset(PERMISSION_ACTIONS), subject_kinds=frozenset({subject_kind})
    )
    subject_ref = f"{subject_kind}:{subject_id}"
    loaded: list[AuditEntry] = []
    position: tuple[datetime, str] | None = None
    read = 0
    while read < READ_CEILING:
        rows = await ledger.window(
            criteria,
            subject=subject_ref,
            position=position,
            newest_first=False,
            limit=LOAD_CHUNK,
        )
        read += len(rows)
        loaded.extend(entry for entry in (entry_from(row) for row in rows) if entry is not None)
        if len(rows) < LOAD_CHUNK:
            break
        position = (rows[-1].at, rows[-1].entry_hash)

    events = permission_history(
        AuditView(loaded, reader=asked.reach, now=asked.now),
        subject_kind=subject_kind,
        subject_id=subject_id,
    )
    return PermissionHistoryView(
        subject_kind=subject_kind,
        subject_id=subject_id,
        events=[
            PermissionEventView(
                at=one.at, action=one.action, actor_id=one.actor_id, details=dict(one.details)
            )
            for one in events
        ],
        full=len(events) >= MAX_PAGE_SIZE,
    )
