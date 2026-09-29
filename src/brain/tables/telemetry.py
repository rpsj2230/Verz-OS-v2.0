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

**The routing decision's columns are names with checks from their enums (M3.4.2, M3.6.3).**
`lane_basis` is the rule that chose the lane, and `routed_tier` and `tier_basis` are where the
executor sent the model call and the step that settled it; migrations 0100 and 0113 add them
nullable, because a row the front half or the executor did not decide for has none.

**The payload store is beside it, and it is the other of the two stores split by classification**
(M27.1.3, M24.3.4). `obs.trace_step` is a run's trace graph, one row per step keyed by the trace
id, and `obs.trace_read` is the row written before anybody reads one. The ledger holds names and
counts and is read widely; the trace holds what a run did and handed back, masked, and is read by
nobody on the application's role: `0150` grants `brain_app` INSERT on the steps and no SELECT, and
only `brain_trace_reader` may read them. **A payload column admits the four strings `mask` can
leave in one and nothing else**, so a payload that did not pass through
`brain.ops.tracing.mask` is refused by the database as well as never built by
`brain.ops.trace_store`.

Task ids: M30.5.2, M3.4.2, M3.6.3, M27.1.3, M24.3.4
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
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import TRACE_ID
from brain.core.lane import Lane
from brain.db import Base
from brain.gate.classify import LaneBasis
from brain.gate.context import TrafficClass
from brain.gate.injection import MAX_SCORE
from brain.gate.select import SelectionStage
from brain.models.routing import Tier, TierBasis
from brain.ops.telemetry import RequestStatus
from brain.ops.tracing import MASKED_PAYLOADS, VALUE_TOKEN_RE, StepKind
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


#: The width of a basis column and of the tier column, each holding its enum's longest member.
BASIS_CHARS: Final = 16
TIER_CHARS: Final = 8

#: The injection score's range, from `brain.gate.injection.MAX_SCORE` rather than restated.
RISK_SCORE_RANGE: Final = f"risk_score IS NULL OR risk_score BETWEEN 0 AND {MAX_SCORE}"


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
    #: The gate's front half, written as it decided (M3.4.2, M3.6.3; migration 0100). Null on a
    #: row the front half did not run for, and on every row written before 0100.
    risk_score: Mapped[int | None] = mapped_column(SmallInteger)
    routed_lane: Mapped[str | None] = mapped_column(String(8))
    selection_stage: Mapped[str | None] = mapped_column(String(16))
    selected_agent: Mapped[str | None] = mapped_column(String(NAME_CHARS))
    #: The rest of the routing decision, as it was decided (M3.6.3; migration 0113).
    lane_basis: Mapped[str | None] = mapped_column(String(BASIS_CHARS))
    routed_tier: Mapped[str | None] = mapped_column(String(TIER_CHARS))
    tier_basis: Mapped[str | None] = mapped_column(String(BASIS_CHARS))

    __table_args__ = (
        CheckConstraint(one_of("traffic_class", TrafficClass), name="traffic_class"),
        CheckConstraint(one_of("lane", Lane), name="lane"),
        CheckConstraint(one_of("status", RequestStatus), name="status"),
        CheckConstraint(ENT_HASH_CHECK, name="ent_hash_shape"),
        CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        CheckConstraint("length(btrim(principal)) >= 1", name="principal_present"),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        CheckConstraint(RISK_SCORE_RANGE, name="risk_score_range"),
        CheckConstraint(
            f"routed_lane IS NULL OR {one_of('routed_lane', Lane)}", name="routed_lane"
        ),
        CheckConstraint(
            f"selection_stage IS NULL OR {one_of('selection_stage', SelectionStage)}",
            name="selection_stage",
        ),
        CheckConstraint(
            f"lane_basis IS NULL OR {one_of('lane_basis', LaneBasis)}", name="lane_basis"
        ),
        CheckConstraint(
            f"routed_tier IS NULL OR {one_of('routed_tier', Tier)}", name="routed_tier"
        ),
        CheckConstraint(
            f"tier_basis IS NULL OR {one_of('tier_basis', TierBasis)}", name="tier_basis"
        ),
        *(_not_negative(one) for one in (*COUNT_COLUMNS, *OPTIONAL_DURATION_COLUMNS)),
        Index("ix_request_telemetry_received_at", "received_at"),
        Index("ix_request_telemetry_trace_id", "trace_id"),
        {"schema": "obs", "postgresql_partition_by": PARTITION_BY},
    )


# ------------------------------------------------------------------ the payload store
#: The width of a step's name: system vocabulary, a lane, a tool or a source.
STEP_NAME_CHARS: Final = 64

#: The width of the reason a payload read states. A reason, not an essay.
READ_REASON_CHARS: Final = 500

#: A step's name, in the grammar `brain.ops.tracing` admits unmasked under a safe key.
STEP_NAME_CHECK: Final = f"name ~ '{VALUE_TOKEN_RE.pattern}'"


def masked(column: str) -> str:
    """The check that a payload column holds one of `MASKED_PAYLOADS` and no other text."""
    return one_of(column, MASKED_PAYLOADS)


class TraceStepRow(Base):
    """`obs.trace_step`. One step of a run's trace graph, masked before it was built (M24.3.4).

    Appended by `brain.ops.trace_store.TraceRecorder` and never updated. The graph is the parent
    column: the request is step zero and has none, and every other step names an earlier one.
    """

    __tablename__ = "trace_step"

    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), primary_key=True)
    step: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    parent: Mapped[int | None] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(STEP_NAME_CHARS), nullable=False)
    #: `brain.ops.tracing.mask`'s attributes: an allowlisted name's value, or a mask token.
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_in: Mapped[str] = mapped_column(Text, nullable=False)
    payload_out: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        CheckConstraint("step >= 0", name="step_not_negative"),
        CheckConstraint(
            "(parent IS NULL) = (step = 0) AND (parent IS NULL OR parent < step)",
            name="a_step_hangs_from_an_earlier_one",
        ),
        CheckConstraint(one_of("kind", StepKind), name="kind"),
        CheckConstraint("(kind = 'request') = (step = 0)", name="the_request_is_step_zero"),
        CheckConstraint(STEP_NAME_CHECK, name="name_is_vocabulary"),
        CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        CheckConstraint(masked("payload_in"), name="payload_in_masked"),
        CheckConstraint(masked("payload_out"), name="payload_out_masked"),
        {"schema": "obs"},
    )


class TraceReadRow(Base):
    """`obs.trace_read`. One look at a stored trace, written before the look (M27.1.3).

    `brain.ops.tracing.PayloadRead` as a row: who, when, which trace and why. Appended by
    `brain.ops.trace_store.StoredTraces.read` in a transaction of its own that commits before the
    trace is read, and never updated.
    """

    __tablename__ = "trace_read"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(READ_REASON_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(actor)) > 0", name="somebody_read_it"),
        CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        CheckConstraint("length(btrim(reason)) > 0", name="a_read_states_why"),
        Index("ix_trace_read_trace_id", "trace_id"),
        {"schema": "obs"},
    )
