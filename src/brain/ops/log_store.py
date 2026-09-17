"""The application log's table side: writing what the capture kept, holding the table to a ceiling,
and the statement the Logs screen reads with.

`brain.ops.log_capture` decides what a row may carry and bounds how fast rows arrive. This module
owns the sessions and decides nothing about content, which is the split `brain.ops.limits` and
`brain.ops.limit_store` make: a writer that also redacted could only be tested through a database.

**Written in batches from the event loop, never from inside a log call.** A structlog processor is
synchronous and runs on whatever thread logged, so a processor that wrote would put a database
round trip inside every warning, on the request path, holding whatever lock the caller held. The
capture keeps rows in memory and `LogStore.run` writes them every `FLUSH_SECONDS` in one
transaction as the application role. A batch that cannot be written is dropped and said so on
standard output and in the next batch, rather than kept, because a writer that kept failed batches
would be a buffer with no bound in front of a database that is already refusing. See
`A_BATCH_THAT_CANNOT_BE_WRITTEN_IS_DROPPED_AND_SAID`.

**The table has a ceiling as well as a window, and they answer different failures.** The retention
sweep removes rows older than the trace window once a person has released it, which is what keeps
an ordinary month's log. It does nothing about a storm inside the month, does nothing while
unreleased, and does nothing while a legal hold names subjects, because this table has no subject
column for a hold to be matched against and `brain.ops.retention_store` refuses a store it cannot
match rather than guessing. So every `TRIM_EVERY_ROWS` rows it writes, a process removes everything
past the newest `MAX_STORED_ROWS`. The arithmetic is `WORST_CASE_ROWS_A_DAY` and
`WORST_CASE_TABLE_BYTES`, and a storm costs the oldest rows rather than the database. See
`A_LOG_HAS_A_CEILING_BECAUSE_A_WINDOW_ONLY_BOUNDS_AGE`.

**The read statement makes no decision.** It selects a window, optionally one level and a search
within event names, newest first by `(at, id)`, one row past the page so a full page says so. Who
may run it is `brain.log_routes.may_read_application_log`, asked before it is built.

Rejected: writing through the retention sweep's executor, so that only one thing ever deletes from
a table. The sweep runs on the worker's schedule in report-only mode until released, and a ceiling
that waited for a release would be a ceiling that is not there on the install where the storm is.

Task ids: M27.8.14
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

import structlog
from sqlalchemy import Delete, Select, delete, insert, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.log_capture import (
    MAX_ROWS_PER_MINUTE,
    Captured,
    LogCapture,
    LogLevel,
    install,
)
from brain.settings import Settings
from brain.tables.application_log import MAX_FIELDS_BYTES, ApplicationLogRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a failed batch is not retried.
A_BATCH_THAT_CANNOT_BE_WRITTEN_IS_DROPPED_AND_SAID: Final = (
    "A batch the database refused is dropped, and the refusal is logged with the exception's "
    "type and the number of rows, which reaches standard output at once and the table in the "
    "next batch that is written. Keeping failed batches to retry would make the memory the "
    "capture bounds unbounded again, exactly while the database is the thing failing."
)

#: Why the table has a ceiling as well as a retention window.
A_LOG_HAS_A_CEILING_BECAUSE_A_WINDOW_ONLY_BOUNDS_AGE: Final = (
    "The retention sweep removes rows past the trace window, once released and while no hold "
    "stops it. That bounds how old a row is and not how many there are, so a storm inside the "
    "window, an install that never released the sweep, and a hold naming subjects would each "
    "leave the table growing. Every writer therefore keeps the table to the newest "
    "MAX_STORED_ROWS, and a storm costs the oldest rows of the log rather than the database."
)

# ------------------------------------------------------------------------ the figures
#: How often waiting rows are written.
FLUSH_SECONDS: Final = 5.0

#: The most rows the table keeps, newest first.
MAX_STORED_ROWS: Final = 100_000

#: How many rows a process writes between two trims.
TRIM_EVERY_ROWS: Final = 500

#: The most rows one process can add in a day: its new rows a minute, and one row a flush saying
#: what was not kept.
WORST_CASE_ROWS_A_DAY: Final = (MAX_ROWS_PER_MINUTE + int(60 / FLUSH_SECONDS)) * 60 * 24

#: The most the table can hold in bytes of fields, before the ceiling trims it: every row at the
#: fields bound, and the trim's own lag of one interval per writer.
WORST_CASE_TABLE_BYTES: Final = (MAX_STORED_ROWS + TRIM_EVERY_ROWS) * MAX_FIELDS_BYTES

#: The page a reader gets when they do not ask, and the most they may ask for.
DEFAULT_PAGE: Final = 50
MAX_PAGE: Final = 200

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND: Final = timedelta(microseconds=1)


# ------------------------------------------------------------------------ writing
def row_values(one: Captured) -> dict[str, object]:
    """One captured row as the columns it is written to."""
    return {
        "at": one.at,
        "last_at": one.last_at,
        "level": one.level.value,
        "event": one.event,
        "origin": one.origin,
        "trace_id": one.trace_id,
        "error_type": one.error_type,
        "repeats": one.repeats,
        "fields": dict(one.fields),
    }


def trim_statement(ceiling: int) -> Delete:
    """Remove every row past the newest `ceiling`, newest judged by `(at, id)`."""
    beyond = (
        select(ApplicationLogRow.id)
        .order_by(ApplicationLogRow.at.desc(), ApplicationLogRow.id.desc())
        .offset(ceiling)
    )
    return delete(ApplicationLogRow).where(ApplicationLogRow.id.in_(beyond))


class LogStore:
    """Writes what one capture kept, in batches, and holds the table to its ceiling."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        capture: LogCapture,
        *,
        ceiling: int = MAX_STORED_ROWS,
        trim_every: int = TRIM_EVERY_ROWS,
        flush_seconds: float = FLUSH_SECONDS,
    ) -> None:
        self.sessions = sessions
        self.capture = capture
        self.ceiling = ceiling
        self.trim_every = trim_every
        self.flush_seconds = flush_seconds
        # A process that has just started trims at its first write, so an install that restarts
        # more often than it writes `trim_every` rows is still held to the ceiling.
        self._since_trim = trim_every

    async def flush(self) -> int:
        """Write every waiting row in one transaction, trimming when due. How many were written."""
        rows = self.capture.drain()
        if not rows:
            return 0
        try:
            async with self.sessions() as session:
                await session.execute(insert(ApplicationLogRow), [row_values(one) for one in rows])
                if self._since_trim + len(rows) >= self.trim_every:
                    await session.execute(trim_statement(self.ceiling))
                    trimmed = True
                else:
                    trimmed = False
                await session.commit()
        except Exception as exc:
            # See A_BATCH_THAT_CANNOT_BE_WRITTEN_IS_DROPPED_AND_SAID.
            log.warning("log_store.unwritten", error=type(exc).__name__, dropped=len(rows))
            return 0
        self._since_trim = 0 if trimmed else self._since_trim + len(rows)
        return len(rows)

    async def run(self, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> None:
        """Write every `flush_seconds` until cancelled."""
        while True:
            await sleep(self.flush_seconds)
            await self.flush()


# ------------------------------------------------------------------------ the process's own
def secrets_of(settings: Settings) -> tuple[str, ...]:
    """Every secret value this process was configured with, for the capture to refuse.

    The role password, the vault token, the trace store's secret key, and the password inside each
    connection address. Read from `Settings` and nowhere else.
    """
    found = [settings.app_role_password, settings.vault_token, settings.langfuse_secret_key]
    for address in (settings.database_url, settings.read_replica_url, settings.valkey_url):
        with contextlib.suppress(ValueError):
            password = urlsplit(address).password
            if password:
                found.append(password)
    return tuple(one for one in found if one)


@dataclass(frozen=True)
class RunningLogStore:
    """What `start_log_store` started, for `stop_log_store` to stop."""

    store: LogStore
    task: asyncio.Task[None]
    uninstall: Callable[[], None]


def start_log_store(
    sessions: async_sessionmaker[AsyncSession] | None, settings: Settings
) -> RunningLogStore | None:
    """Install the capture and start writing, or None when there is nowhere to write.

    Called from `brain.app.lifespan` once the sessions exist. A process whose structlog already has
    a capture installed starts nothing, and says so, rather than writing every row twice.
    """
    if sessions is None:
        return None
    capture = LogCapture(known_secrets=secrets_of(settings))
    try:
        uninstall = install(capture)
    except RuntimeError:
        log.warning("log_store.already_capturing")
        return None
    store = LogStore(sessions, capture)
    return RunningLogStore(store=store, task=asyncio.create_task(store.run()), uninstall=uninstall)


async def stop_log_store(running: RunningLogStore | None) -> None:
    """Stop writing, write what is waiting, and take the capture out of structlog."""
    if running is None:
        return
    running.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await running.task
    try:
        await running.store.flush()
    finally:
        running.uninstall()


# ------------------------------------------------------------------------ reading
#: The columns a page is read with, in order.
ENTRY_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "at",
    "last_at",
    "level",
    "event",
    "origin",
    "trace_id",
    "error_type",
    "repeats",
    "fields",
)


def escape_like(text: str) -> str:
    """`text` with the three characters `LIKE` gives a meaning escaped, so a search is literal."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def cursor_of(at: datetime, row_id: int) -> str:
    """The position after a row, as text: its instant in whole microseconds, and its id."""
    return f"{(at - _EPOCH) // _MICROSECOND}.{row_id}"


def position_of(cursor: str) -> tuple[datetime, int]:
    """The position a cursor names. Raises `ValueError` on anything `cursor_of` did not write."""
    instant, dot, row_id = cursor.partition(".")
    if not (dot and instant.isdigit() and row_id.isdigit() and len(instant) <= 18):
        msg = "malformed cursor"
        raise ValueError(msg)
    return _EPOCH + int(instant) * _MICROSECOND, int(row_id)


def entries(
    *,
    start: datetime,
    end: datetime,
    level: LogLevel | None,
    event: str | None,
    after: tuple[datetime, int] | None,
    limit: int,
) -> Select[tuple[Any, ...]]:
    """Rows in `[start, end)`, newest first, narrowed as asked, one past `limit`."""
    statement = select(*(getattr(ApplicationLogRow, name) for name in ENTRY_COLUMNS)).where(
        ApplicationLogRow.at >= start, ApplicationLogRow.at < end
    )
    if level is not None:
        statement = statement.where(ApplicationLogRow.level == level.value)
    if event:
        statement = statement.where(
            ApplicationLogRow.event.ilike(f"%{escape_like(event)}%", escape="\\")
        )
    if after is not None:
        statement = statement.where(
            tuple_(ApplicationLogRow.at, ApplicationLogRow.id)
            < tuple_(literal(after[0]), literal(after[1]))
        )
    return statement.order_by(ApplicationLogRow.at.desc(), ApplicationLogRow.id.desc()).limit(
        limit + 1
    )


def fields_of(stored: object) -> Mapping[str, str]:
    """A row's fields as short strings, whatever a hand-written statement put in the column."""
    if not isinstance(stored, dict):
        return {}
    return {str(key): str(value) for key, value in stored.items()}
