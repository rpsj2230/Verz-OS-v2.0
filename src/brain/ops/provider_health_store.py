"""The statements behind provider health, chain-depth alerts, tier rules and residency constraints.

`brain.models.calls` decides; this holds the SQL, for the layout's rule that nothing deciding
policy owns a client. Four things are read with the ladder on every planned call
(`brain.ops.model_service.SessionLadder`): the tier rows, the residency constraints, the stored
rings. Two are written by the live path: a live outcome appended to its ring, and a depth alert.
Two by the worker's prober: a probe claimed, and its outcome appended.

**An append is one statement and never a read followed by a write.** `ops.ring_push` runs inside
the `UPDATE` of an upsert, under the row's lock, so two server processes appending to one ring at
once each land an entry. A read-modify-write from Python would lose one of them, which is exactly
the race `brain.models.evidence` gave as its reason not to store a breaker. See
`AN_APPEND_IS_ONE_STATEMENT_SO_TWO_WRITERS_BOTH_LAND`.

**A probe is claimed by a conditional upsert that returns the row only when it was due.** Two
ticks on two replicas are already serialised by the scheduler's advisory lock, and the claim is the
second line: an upsert whose `WHERE` refuses a deployment probed inside the interval returns
nothing, and the prober sends nothing for it. That is `health.ProviderHealth.claim_probe`'s stamp
("two workers running the same sixty-second tick do not both probe one idle deployment"), in the
table where every process can see it.

**A row the router cannot use is left out and logged, never guessed at.** A tier row with a key
the router does not read is a tier at its compiled numbers, which the Models screen says; a
residency row whose scope does not parse is not applied and is logged at error, because an
unreadable constraint is a policy not in force and the person who wrote it must hear so.

**Writes from the live path never raise**, for `brain.ops.question_store.
A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`.

Task ids: M5.2.2, M5.4.3, M5.4.7, M5.4.8, M5.5.1
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import Select, bindparam, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Insert, ReturningInsert, Update

from brain.core.scope import Scope
from brain.models.evidence import LIVE_RING_CAP, PROBE_RING_CAP, RingEntry, StoredRings, ring_of
from brain.models.health import DepthAlert
from brain.models.residency import ResidencyError, ScopedResidency, requirement_of
from brain.models.tier_rules import TierRule, TierRuleError, rule_of
from brain.tables.model_health import (
    ChainDepthAlertRow,
    ProviderHealthRow,
    ResidencyConstraintRow,
)
from brain.tables.routing import RoutingTierRow

log = structlog.get_logger(__name__)

#: Why a ring is appended in SQL.
AN_APPEND_IS_ONE_STATEMENT_SO_TWO_WRITERS_BOTH_LAND: Final = (
    "Every server process appends to the same ring after its own attempts. Read, append in "
    "Python and write back, and two processes finishing together each write a ring missing the "
    "other's entry. ops.ring_push runs inside the upsert's UPDATE, under the row lock, so the "
    "second append sees the first."
)

#: The most rows of each kind one read takes. Resource bounds far above any real install.
MAX_RINGS: Final = 500
MAX_CONSTRAINTS: Final = 200
MAX_ALERTS: Final = 50


# ------------------------------------------------------------------------------ the reads


def live_tiers() -> Select[tuple[RoutingTierRow]]:
    """Every live tier row. `deleted_at` tested here as well as by policy."""
    return (
        select(RoutingTierRow)
        .where(RoutingTierRow.deleted_at.is_(None))
        .order_by(RoutingTierRow.tier)
    )


def live_constraints() -> Select[tuple[ResidencyConstraintRow]]:
    """Every live residency constraint, oldest first, bounded."""
    return (
        select(ResidencyConstraintRow)
        .where(ResidencyConstraintRow.deleted_at.is_(None))
        .order_by(ResidencyConstraintRow.created_at, ResidencyConstraintRow.id)
        .limit(MAX_CONSTRAINTS)
    )


def stored_rings() -> Select[tuple[ProviderHealthRow]]:
    """Every deployment's stored rings, bounded."""
    return select(ProviderHealthRow).order_by(ProviderHealthRow.deployment_id).limit(MAX_RINGS)


def recent_alerts(since: datetime) -> Select[tuple[ChainDepthAlertRow]]:
    """The newest depth alerts raised since `since`, newest first, bounded."""
    return (
        select(ChainDepthAlertRow)
        .where(ChainDepthAlertRow.raised_at >= since)
        .order_by(ChainDepthAlertRow.raised_at.desc(), ChainDepthAlertRow.id)
        .limit(MAX_ALERTS)
    )


def tier_rules_of(rows: Sequence[RoutingTierRow]) -> tuple[TierRule, ...]:
    """The rows the router can use. `none` and an unreadable row are left out; see the module."""
    found: list[TierRule] = []
    for row in rows:
        if row.tier == "none":
            continue
        try:
            found.append(rule_of(row.tier, row.context_window, row.rules))
        except TierRuleError as exc:
            log.warning("models.tier_row_unreadable", tier=row.tier, error=str(exc))
    return tuple(found)


def constraint_of(row: ResidencyConstraintRow) -> ScopedResidency | None:
    """One stored constraint, or None, logged at error, when it cannot be applied."""
    try:
        return ScopedResidency(
            scope=Scope.model_validate(row.scope),
            requirement=requirement_of(row.allowed_regions, on_prem_only=row.on_prem_only),
            reason=row.note,
        )
    except (ValidationError, ResidencyError, TypeError) as exc:
        log.error(
            "models.residency_constraint_unreadable",
            constraint=str(row.id),
            error=type(exc).__name__,
        )
        return None


def rings_of(row: ProviderHealthRow) -> StoredRings:
    """One row's rings, each entry read leniently by `evidence.ring_of`."""
    return StoredRings(
        deployment_id=row.deployment_id,
        provider=row.provider,
        live=ring_of(row.live),
        probe=ring_of(row.probe),
        last_live_at=row.last_live_at,
        last_probe_at=row.last_probe_at,
    )


# ----------------------------------------------------------------------------- the writes


def _entry(ok: bool, at: datetime) -> Any:
    """One ring entry as a jsonb parameter."""
    return bindparam(None, RingEntry(ok=ok, at=at).stored(), type_=JSONB)


def live_observed(deployment_id: str, provider: str, *, ok: bool, at: datetime) -> Insert:
    """Append one live outcome to a deployment's ring, creating the row on its first."""
    added = pg_insert(ProviderHealthRow).values(
        deployment_id=deployment_id,
        provider=provider,
        live=[RingEntry(ok=ok, at=at).stored()],
        last_live_at=at,
    )
    return added.on_conflict_do_update(
        index_elements=[ProviderHealthRow.deployment_id],
        set_={
            "provider": added.excluded.provider,
            "live": func.ops.ring_push(ProviderHealthRow.live, _entry(ok, at), LIVE_RING_CAP),
            "last_live_at": func.greatest(ProviderHealthRow.last_live_at, at),
            "updated_at": func.now(),
        },
    )


def probe_claimed(
    deployment_id: str, provider: str, *, at: datetime, interval: timedelta
) -> ReturningInsert[tuple[str]]:
    """Claim one deployment's probe at `at`, returning its id only when it was due.

    A row probed inside `interval` is left alone and nothing comes back. See the module docstring.
    """
    added = pg_insert(ProviderHealthRow).values(
        deployment_id=deployment_id, provider=provider, last_probe_at=at
    )
    return added.on_conflict_do_update(
        index_elements=[ProviderHealthRow.deployment_id],
        set_={"last_probe_at": at, "updated_at": func.now()},
        where=or_(
            ProviderHealthRow.last_probe_at.is_(None),
            ProviderHealthRow.last_probe_at <= at - interval,
        ),
    ).returning(ProviderHealthRow.deployment_id)


def probe_observed(deployment_id: str, *, ok: bool, at: datetime) -> Update:
    """Append one probe outcome to the ring of a deployment whose probe was claimed."""
    return (
        update(ProviderHealthRow)
        .where(ProviderHealthRow.deployment_id == deployment_id)
        .values(
            probe=func.ops.ring_push(ProviderHealthRow.probe, _entry(ok, at), PROBE_RING_CAP),
            updated_at=func.now(),
        )
    )


def alert_recorded(alert: DepthAlert, *, trace_id: str, at: datetime) -> Insert:
    """One depth alert, as the live path raised it."""
    return insert(ChainDepthAlertRow).values(
        trace_id=trace_id,
        raised_at=at,
        level=alert.level.value,
        tier=alert.tier.value,
        depth=alert.depth,
        served_by=alert.served_by,
        reason=alert.reason[:600],
    )


# ----------------------------------------------------------------------------- the stores


class SessionHealth:
    """`brain.models.calls.HealthLog` over `ops.provider_health`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def observed(self, *, deployment_id: str, provider: str, ok: bool, at: datetime) -> None:
        """Append the outcome. A ring that cannot be written does not stop the call."""
        try:
            async with self.sessions() as session:
                await session.execute(live_observed(deployment_id, provider, ok=ok, at=at))
                await session.commit()
        except Exception as exc:
            log.warning(
                "models.health_unrecorded", deployment=deployment_id, error=type(exc).__name__
            )


class SessionDepthAlerts:
    """`brain.models.calls.DepthAlerts` over `ops.chain_depth_alert`, and the log."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession] | None) -> None:
        self.sessions = sessions

    async def raised(self, alert: DepthAlert, *, trace_id: str, at: datetime) -> None:
        """Say the alert in the log at its level, then keep it. Never raises.

        The log line comes first and carries the same sentence, so an alert whose row could not be
        written still reaches whatever reads the log. It names a tier, a depth and a deployment,
        never a question.
        """
        emit = log.error if alert.level.value == "critical" else log.warning
        emit(
            "models.chain_depth",
            level=alert.level.value,
            tier=alert.tier.value,
            depth=alert.depth,
            served_by=alert.served_by,
            reason=alert.reason,
            trace_id=trace_id,
        )
        if self.sessions is None:
            return
        try:
            async with self.sessions() as session:
                await session.execute(alert_recorded(alert, trace_id=trace_id, at=at))
                await session.commit()
        except Exception as exc:
            log.warning("models.chain_depth_unrecorded", error=type(exc).__name__)
