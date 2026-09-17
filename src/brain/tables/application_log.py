"""The application's warnings and errors, as rows the Logs screen reads: names, shapes and counts.

`brain.ops.log_capture` decides what a row may carry and `brain.ops.log_store` writes it. This is
the table, and `migrations/versions/0063_application_log.py` builds it.

**`obs`, because `brain.db.SCHEMAS` says traces live there, and the retention sweep reaches it as a
trace.** `brain.ops.retention_store.ATTRIBUTED` names the table as the trace store's, with `at` as
its clock, so a row leaves after `brain.ops.retention.TRACE_RETENTION_DAYS` once the sweep is
released, by the same run and under the same holds as every other fixed window. A log row is the
shape of something that happened in a run, which is what the trace class is, and it holds no
content, which is why it can share the trace window rather than needing a shorter one.

**Every column is a name, a shape, a count or an instant.** The event is a literal from the source
or null; the origin is a module and a line; the reference is a trace id in the shape this system
mints; the error is an exception's type; `fields` is a flat object of short strings the capture
kept or masked. No column is wide enough for a paragraph, and `fields` is bounded in bytes by a
check, so a writer that got the capture wrong is refused by the database rather than trusted by it.

**No `deleted_at` and no update.** A log row is a fact about a moment and is never edited. It leaves
in two ways only: by age, through the sweep, and by volume, through `brain.ops.log_store`'s
ceiling, which is why the application role is granted DELETE here where most tables are not.

**A bigint identity rather than a uuid.** Rows are paged newest first by `(at, id)` and the ceiling
removes everything past the newest few hundred thousand, and both are an index range on a small key.

Task ids: M27.8.14
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.log_capture import MAX_EVENT_CHARS, MAX_ORIGIN_CHARS, LogLevel
from brain.tables.identity import one_of

#: The width of a trace reference, as `brain.audit.ledger.TRACE_ID` bounds one.
TRACE_ID_CHARS: Final = 64

#: The width of an exception's type name, as `brain.ops.log_capture` bounds one.
ERROR_TYPE_CHARS: Final = 80

#: The most bytes a row's fields may take. Sixteen fields of a short key and a short value fit well
#: inside it, so reaching it means a writer that did not go through the capture.
MAX_FIELDS_BYTES: Final = 4096


class ApplicationLogRow(Base):
    """`obs.application_log`. One warning, error or sampled info call, and how often it repeated."""

    __tablename__ = "application_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    #: When the first of the calls this row stands for was made.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the last of them was made. Equal to `at` for a call that did not repeat.
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    #: The event name, or null when it was not a literal in the source.
    event: Mapped[str | None] = mapped_column(String(MAX_EVENT_CHARS))
    #: `module:line`, or null when no call site was found.
    origin: Mapped[str | None] = mapped_column(String(MAX_ORIGIN_CHARS))
    trace_id: Mapped[str | None] = mapped_column(String(TRACE_ID_CHARS))
    error_type: Mapped[str | None] = mapped_column(String(ERROR_TYPE_CHARS))
    repeats: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(one_of("level", LogLevel), name="level"),
        CheckConstraint("repeats >= 1", name="repeats_positive"),
        CheckConstraint("last_at >= at", name="last_not_before_first"),
        CheckConstraint("jsonb_typeof(fields) = 'object'", name="fields_object"),
        CheckConstraint(f"octet_length(fields::text) <= {MAX_FIELDS_BYTES}", name="fields_bounded"),
        Index("ix_application_log_at", "at", "id"),
        {"schema": "obs"},
    )
