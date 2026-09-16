"""The metadata ledger, as rows: one per request the answer lane finished, names and counts only.

`brain.ops.telemetry.RequestTelemetry` has been the record since M27.1.5 and nothing held one.
This is the table, and it holds `RequestTelemetry.ledger_row` key for key plus a surrogate id.
A test compares the columns against the keys a real record produces, so a field added to the
record and not to the table fails a build rather than the first write in production.

**`obs`, because `brain.db.SCHEMAS` says that is where the metadata ledger lives.** The question
table went to `ops` beside the spend ledger it is read with; this one is the ledger `obs` is
declared for, and the audit chain beside it is the other half of reconstructing a request.

**Partitioned by range on `received_at` from the first migration, with a default partition.**
`brain.ops.partitioning` derives the scheme and records converting a populated table as the
change that cannot be undone cheaply, because it rewrites the table. The monthly partitions
`brain.ops.ledger_partitions` makes (M36.1.1.1) are created under an existing partitioned parent,
so creating the parent partitioned now left that leaf a statement per month rather than a rewrite.
The primary key is `(id, received_at)` because a key on
a partitioned table has to include the partition key, and `partitioning.CONTROL_COLUMN` is what a
test holds the server's partition key to.

**A surrogate id rather than the trace id as the key, which is the opposite of the question
table, deliberately.** `ops.question_asked` keeps the first record of a trace because a question
is a person's act and a reused trace id must not count it twice. A latency objective is about
requests, and the middleware accepts a caller-proposed trace id, so two requests can finish under
one id: keying on it would drop the second request's duration, and a caller could keep their slow
requests out of the percentile by reusing an id.

**Nothing about what was asked or what came back.** Every column is a name, a count, a hash, a
duration or a flag, which is `brain.ops.telemetry`'s
`THE_LEDGER_HOLDS_NAMES_AND_COUNTS_AND_NEVER_A_VALUE` and is why the table can be kept for the
metadata ledger's window. The status is the coarse one,
so a withheld record and an absent one are the same row but for the trace, the instants and the
duration.

Task ids: M30.5.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.lane import Lane
from brain.db import Base
from brain.gate.context import TrafficClass
from brain.ops.telemetry import RequestStatus
from brain.tables.adoption import TRACE_ID_CHARS
from brain.tables.identity import one_of
from brain.tables.spend import NAME_CHARS, PRINCIPAL_ID_CHARS

#: The width of an entitlement hash: thirty-two hex characters, as `brain.audit.ledger.ENT_HASH`.
ENT_HASH_CHARS: Final = 32

#: The shape check on the hash, the same predicate `0002` puts on the audit entry's.
ENT_HASH_CHECK: Final = r"entitlement_hash ~ '^[0-9a-f]{32}$'"

#: How a period is routed, in PostgreSQL's words. See the module docstring.
PARTITION_BY: Final = "RANGE (received_at)"

#: The count columns, each refused below zero and each allowed to be absent.
COUNT_COLUMNS: Final[tuple[str, ...]] = (
    "tokens_in",
    "tokens_out",
    "tool_count",
    "redaction_count",
    "fallback_count",
    "retry_count",
)

#: The duration columns nothing measures yet, each refused below zero and allowed to be absent.
OPTIONAL_DURATION_COLUMNS: Final[tuple[str, ...]] = ("time_to_first_token_ms", "tool_latency_ms")


def _not_negative(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IS NULL OR {column} >= 0", name=f"{column}_not_negative")


class RequestTelemetryRow(Base):
    """`obs.request_telemetry`. One request the answer lane finished (M30.5.2).

    Appended by `brain.ops.telemetry_store.record` and never updated: how a request went does
    not change afterwards, and a period leaves the ledger by its partition being detached.
    """

    __tablename__ = "request_telemetry"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    #: When the gate judged the request. The partition key and the window a reading takes.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    traffic_class: Mapped[str] = mapped_column(String(24), nullable=False)
    principal: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    policy_epoch: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    entitlement_hash: Mapped[str] = mapped_column(String(ENT_HASH_CHARS), nullable=False)
    lane: Mapped[str] = mapped_column(String(8), nullable=False)
    model: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    provider: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    time_to_first_token_ms: Mapped[float | None] = mapped_column(Float)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    tool_count: Mapped[int | None] = mapped_column(Integer)
    tool_latency_ms: Mapped[float | None] = mapped_column(Float)
    connector: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    redaction_count: Mapped[int | None] = mapped_column(Integer)
    fallback_count: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("traffic_class", TrafficClass), name="traffic_class"),
        CheckConstraint(one_of("lane", Lane), name="lane"),
        CheckConstraint(one_of("status", RequestStatus), name="status"),
        CheckConstraint(ENT_HASH_CHECK, name="ent_hash_shape"),
        CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        CheckConstraint("length(btrim(principal)) >= 1", name="principal_present"),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        *(_not_negative(one) for one in (*COUNT_COLUMNS, *OPTIONAL_DURATION_COLUMNS)),
        Index("ix_request_telemetry_received_at", "received_at"),
        Index("ix_request_telemetry_trace_id", "trace_id"),
        {"schema": "obs", "postgresql_partition_by": PARTITION_BY},
    )
