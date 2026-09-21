"""Where a provider's health, the chain's depth and a scope's residency constraint are kept.

Three tables `0108` adds, each the storage for a sentence the routing leaves wrote and nothing
persisted.

**`ops.provider_health`: one row per deployment, with a live ring and a probe ring** (M5.4.3). The
executor appends every attempt that answered or failed on the provider's side to `live`, and the
worker's prober (`brain.ops.model_probe_run`) appends each probe to `probe`. The rings are jsonb
arrays of `{"ok", "at"}`, capped by a check at the windows `brain.models.health` reads, and appended
by one `UPDATE` through `ops.ring_push`, so two processes appending at once each land an entry
rather than one overwriting the other: the race `brain.models.evidence` gave as the reason not to
store a breaker is a race over a whole value, and this is an append under the row's lock. The
breaker is still replayed; see `brain.models.evidence` for what each ring adds. `last_probe_at` is
when a probe was last *claimed*, which is how two ticks never probe one deployment twice.

**`ops.chain_depth_alert`: one row per alert the live path raised** (M5.4.8). Append-only, and it
names a tier, a depth and the deployment that served, never a question: the rule in
`brain.ops.alerting.AN_ALERT_BODY_NAMES_A_MECHANISM_AND_NEVER_A_SUBJECT`. The trace id is kept so an
operator can open the attempts that went deep.

**`ops.residency_constraint`: a scope and the regions it allows** (M5.5.1). `scope` is
`Scope.model_dump()`, checked by the grant tables' own `SCOPE_SHAPE`; `allowed_regions` is null for
"any region" (with `on_prem_only` then required) or a non-empty array. Retired by `deleted_at`, so
the row that was in force when a question was refused can still be read.

Task ids: M5.4.3, M5.4.8, M5.5.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import TRACE_ID
from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.models.evidence import LIVE_RING_CAP, PROBE_RING_CAP
from brain.models.health import AlertLevel
from brain.models.routing import Tier
from brain.tables.gate import SCOPE_SHAPE
from brain.tables.identity import one_of
from brain.tables.routing import DEPLOYMENT_ID_CHARS, PROVIDER_CHARS, TRACE_ID_CHARS

#: The longest alert sentence kept. `health.assess_chain_depth` writes one line naming a tier, a
#: depth and at most a few deployment ids.
REASON_CHARS = 600

#: The longest note an administrator may attach to a residency constraint.
NOTE_CHARS = 500

#: Who created a constraint: a principal id.
PERSON_CHARS = 128


class ProviderHealthRow(Base):
    """`ops.provider_health`. One deployment's stored rings (M5.4.3)."""

    __tablename__ = "provider_health"

    deployment_id: Mapped[str] = mapped_column(String(DEPLOYMENT_ID_CHARS), primary_key=True)
    provider: Mapped[str] = mapped_column(String(PROVIDER_CHARS), nullable=False)
    live: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    probe: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    last_live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When a probe was last claimed, not when one answered: see the module docstring.
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("jsonb_typeof(live) = 'array'", name="live_array"),
        CheckConstraint("jsonb_typeof(probe) = 'array'", name="probe_array"),
        CheckConstraint(f"jsonb_array_length(live) <= {LIVE_RING_CAP}", name="live_capped"),
        CheckConstraint(f"jsonb_array_length(probe) <= {PROBE_RING_CAP}", name="probe_capped"),
        CheckConstraint("length(btrim(deployment_id)) > 0", name="deployment_present"),
        {"schema": "ops"},
    )


class ChainDepthAlertRow(Base):
    """`ops.chain_depth_alert`. One alert the live path raised on a chain's depth (M5.4.8)."""

    __tablename__ = "chain_depth_alert"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    served_by: Mapped[str | None] = mapped_column(String(DEPLOYMENT_ID_CHARS), nullable=True)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("level", AlertLevel), name="level"),
        CheckConstraint(one_of("tier", Tier), name="tier"),
        CheckConstraint("depth >= 1", name="depth_positive"),
        CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        Index("ix_ops_chain_depth_alert_raised_at", "raised_at"),
        {"schema": "ops"},
    )


class ResidencyConstraintRow(TimestampMixin, SoftDeleteMixin, Base):
    """`ops.residency_constraint`. A scope and the regions its requests may be processed in."""

    __tablename__ = "residency_constraint"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: Null for any region, which then needs `on_prem_only`; else a non-empty array of names.
    allowed_regions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    on_prem_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    note: Mapped[str] = mapped_column(String(NOTE_CHARS), nullable=False, server_default="")
    created_by: Mapped[str] = mapped_column(String(PERSON_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(SCOPE_SHAPE, name="scope_shape"),
        CheckConstraint(
            "allowed_regions IS NULL OR (jsonb_typeof(allowed_regions) = 'array' "
            "AND jsonb_array_length(allowed_regions) > 0)",
            name="regions_non_empty_array",
        ),
        # `brain.models.residency.requirement_of` refuses a constraint demanding nothing; this is
        # the same rule where the rows live.
        CheckConstraint("allowed_regions IS NOT NULL OR on_prem_only", name="demands_something"),
        {"schema": "ops"},
    )


#: Every table this module declares, in the order `0108` creates them.
MODEL_HEALTH_TABLES: tuple[str, ...] = (
    "ops.provider_health",
    "ops.chain_depth_alert",
    "ops.residency_constraint",
)
