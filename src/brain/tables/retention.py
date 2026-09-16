"""Legal holds, retention reports and the release of the sweep get rows.

`brain.ops.retention_store` holds the argument for what reads and writes these. What is here is
the three shapes, and each exists because a decision about deleting data was being made with
nothing written down.

**`obs.legal_hold` is `brain.audit.ledger.LegalHold`, column for column, plus who placed it and
who lifted it.** A predicate over subjects rather than a flag on rows, for the reason that model
gives: a hold covers rows written after it was placed. `reason_code` keeps the model's field-name
grammar, because a free-text reason on a hold is where the parties' names end up. **A lifted hold
is marked, never removed**: `released_at` and `released_by` are set once and the row stays,
because which rows were held, on whose word and for how long is asked about later. In `obs`
beside the audit chain, and attributed to the audit store by `brain.ops.retention_store`, so it
is kept for as long as the chain it explains.

**`ops.retention_report` is one run's report, whole.** The run record in `ops.control_run` holds
a sentence of at most `brain.tables.schedule.DETAIL_CHARS`, and a report over seventeen stores
with its findings does not fit in one, so what an administrator read was whatever survived the
cut. Here the stores, the cited holds and the findings are JSON documents and `failure` says why a
run that raised removed nothing. Counts only: see
`brain.ops.retention.A_RETENTION_REPORT_COUNTS_AND_NEVER_NAMES`.

**`ops.retention_release` is the record that a person read a report and decided.** It names the
report they released after, by key, so a release cannot exist before a report does, and it is
withdrawn by being marked rather than removed. At most one live release, by a partial unique
index, because two live releases would make withdrawing one a withdrawal that changes nothing.

Task ids: M25.1.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import FIELD_NAME, IDENTIFIER
from brain.db import Base

#: Widths, named once so the model, the migration and the store agree.
HOLD_ID_CHARS: Final = 128
REASON_CODE_CHARS: Final = 80
PRINCIPAL_CHARS: Final = 128
#: What a failed run's reason may hold. A sentence, for the reason `ops.control_run.detail` is.
FAILURE_CHARS: Final = 2000

#: `FIELD_NAME` with its non-capturing group made an ordinary one, which matches identically.
#: `brain.knowledge.search._posix_pattern` records why: a check constraint is wrapped in
#: `sqlalchemy.text`, which can read a colon as a bind parameter and render it as NULL.
REASON_CODE_PATTERN: Final = FIELD_NAME.replace("(?:", "(")
assert ":" not in REASON_CODE_PATTERN


class LegalHoldRow(Base):
    """`obs.legal_hold`. One hold, from the moment it was placed, kept after it is lifted."""

    __tablename__ = "legal_hold"

    id: Mapped[str] = mapped_column(String(HOLD_ID_CHARS), primary_key=True)
    reason_code: Mapped[str] = mapped_column(String(REASON_CODE_CHARS), nullable=False)
    subjects: Mapped[list[str]] = mapped_column(
        ARRAY(String(PRINCIPAL_CHARS)), nullable=False, server_default=text("'{}'")
    )
    actors: Mapped[list[str]] = mapped_column(
        ARRAY(String(PRINCIPAL_CHARS)), nullable=False, server_default=text("'{}'")
    )
    all_subjects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    placed_by: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(f"id ~ '{IDENTIFIER}'", name="id_is_an_identifier"),
        CheckConstraint(f"reason_code ~ '{REASON_CODE_PATTERN}'", name="reason_is_a_code"),
        CheckConstraint(f"placed_by ~ '{IDENTIFIER}'", name="placed_by_is_an_identifier"),
        # `LegalHold.model_post_init`'s refusal, in the database: a hold naming nothing holds
        # nothing, and nothing would complain until the data it was meant to keep was gone.
        CheckConstraint(
            "all_subjects OR cardinality(subjects) > 0 OR cardinality(actors) > 0",
            name="names_something",
        ),
        # Lifted with a name and an instant, or not lifted: a lift with no one behind it is a
        # hold that stopped for no recorded reason.
        CheckConstraint(
            "(released_at IS NULL AND released_by IS NULL) OR "
            "(released_at IS NOT NULL AND released_by IS NOT NULL)",
            name="lifted_by_somebody",
        ),
        CheckConstraint(
            "released_at IS NULL OR released_at >= placed_at",
            name="lifted_after_it_was_placed",
        ),
        Index("ix_legal_hold_placed_at", "placed_at"),
        {"schema": "obs"},
    )


class RetentionReportRow(Base):
    """`ops.retention_report`. What one sweep found, did and could not do. Never edited."""

    __tablename__ = "retention_report"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The instant the run was asked about, which is the instant every count is as of.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: `brain.ops.retention_store.report_document`'s `stores`.
    stores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    #: The holds active at `at`, cited by identifier and reason code only.
    holds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    findings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    #: Why the run raised, when it did. A run that raised removed nothing.
    failure: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("jsonb_typeof(stores) = 'array'", name="stores_list"),
        CheckConstraint("jsonb_typeof(holds) = 'array'", name="holds_list"),
        CheckConstraint("jsonb_typeof(findings) = 'array'", name="findings_list"),
        CheckConstraint(
            f"failure IS NULL OR length(failure) BETWEEN 1 AND {FAILURE_CHARS}",
            name="failure_is_a_sentence",
        ),
        Index("ix_retention_report_at", "at"),
        {"schema": "ops"},
    )


class RetentionReleaseRow(Base):
    """`ops.retention_release`. A person released the sweep after reading one report."""

    __tablename__ = "retention_release"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    after_report: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ops.retention_report.id"), nullable=False
    )
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_by: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(f"released_by ~ '{IDENTIFIER}'", name="by_is_an_identifier"),
        CheckConstraint(
            "(withdrawn_at IS NULL AND withdrawn_by IS NULL) OR "
            "(withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL)",
            name="withdrawn_by_somebody",
        ),
        CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= released_at",
            name="withdrawn_after_it_was_released",
        ),
        Index(
            "uq_retention_release_live",
            text("(withdrawn_at IS NULL)"),
            unique=True,
            postgresql_where=text("withdrawn_at IS NULL"),
        ),
        {"schema": "ops"},
    )
