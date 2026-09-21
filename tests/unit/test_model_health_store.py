"""The statements behind provider health, depth alerts, tier rules and residency, against a server.

The first half needs no database: the migration's copied figures are held to the code's, and the
statements are compiled and read for the shape that makes an append safe. The second half runs
every statement against a scratch PostgreSQL, which CI provides.

Task ids: M5.4.3, M5.4.7, M5.4.8, M5.5.1, M5.2.2
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.models.evidence import LIVE_RING_CAP, PROBE_RING_CAP
from brain.models.health import PROBE_WINDOW, AlertLevel, DepthAlert
from brain.models.routing import BREAKER_LIVE_WINDOW, Tier
from brain.ops.model_service import SessionLadder
from brain.ops.provider_health_store import (
    SessionDepthAlerts,
    SessionHealth,
    live_observed,
    probe_claimed,
    probe_observed,
    recent_alerts,
)
from brain.tables import model_health, routing
from tests.fixtures.scratch_postgres import engine, modelled, run, sql

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
AT = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)


def migration() -> ModuleType:
    path = MIGRATION / "0108_provider_health_and_residency.py"
    spec = importlib.util.spec_from_file_location("m0108", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=DIALECT))


# ------------------------------------------------------------------------ without a server
def test_the_migrations_copied_figures_are_the_codes() -> None:
    """Held against the windows the health layer reads, not the constants against themselves.

    Delete this and the ring's check could cap it below the window the breaker judges over, so a
    ring the table accepts would be one the breaker reads short."""
    m = migration()

    assert m.LIVE_RING_CAP == LIVE_RING_CAP == BREAKER_LIVE_WINDOW
    assert m.PROBE_RING_CAP == PROBE_RING_CAP == PROBE_WINDOW
    assert m.DEPLOYMENT_ID_CHARS == routing.DEPLOYMENT_ID_CHARS
    assert m.PROVIDER_CHARS == routing.PROVIDER_CHARS
    assert m.TRACE_ID_CHARS == routing.TRACE_ID_CHARS
    assert m.REASON_CHARS == model_health.REASON_CHARS
    assert m.NOTE_CHARS == model_health.NOTE_CHARS
    assert m.PERSON_CHARS == model_health.PERSON_CHARS
    assert m.down_revision == "0105"


def test_an_append_is_one_upsert_through_ring_push_and_never_a_read_then_a_write() -> None:
    """`AN_APPEND_IS_ONE_STATEMENT_SO_TWO_WRITERS_BOTH_LAND`, read off the compiled SQL.

    Delete this and a later edit could append in Python from a read, which loses one of two
    processes' outcomes every time they finish together."""
    live_statement = live_observed("d", "anthropic", ok=True, at=AT)
    probe_statement = probe_observed("d", ok=False, at=AT)
    live, probe = compiled(live_statement), compiled(probe_statement)

    assert "ON CONFLICT (deployment_id) DO UPDATE" in live
    assert "live = ops.ring_push(ops.provider_health.live, " in live
    assert "probe=ops.ring_push(ops.provider_health.probe, " in probe
    assert live_statement.compile(dialect=DIALECT).params["ring_push_1"] == LIVE_RING_CAP
    assert probe_statement.compile(dialect=DIALECT).params["ring_push_1"] == PROBE_RING_CAP


def test_a_claim_updates_only_a_row_probed_before_the_interval_and_returns_the_row() -> None:
    """Delete this and the claim could stamp every row whatever its last probe, so two ticks
    would both probe one deployment in a minute."""
    claim = compiled(probe_claimed("d", "anthropic", at=AT, interval=timedelta(seconds=60)))

    assert "ON CONFLICT (deployment_id) DO UPDATE" in claim
    assert "WHERE ops.provider_health.last_probe_at IS NULL OR" in claim
    assert "RETURNING ops.provider_health.deployment_id" in claim


# ------------------------------------------------------------------------- with a server
TABLES = (
    "ops.routing_rung",
    "ops.model_attempt",
    "ops.setting",
    "ops.model_provider",
    "ops.routing_tier",
    "ops.residency_constraint",
    "ops.provider_health",
    "ops.chain_depth_alert",
)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with modelled("brain_test_model_health_store", TABLES) as url:
        sql(url, migration().RING_PUSH)
        yield url


def test_a_ring_keeps_its_newest_entries_up_to_its_cap_and_a_claim_is_granted_once(
    database: str,
) -> None:
    """**M5.4.3 against a server.** Twenty-five live outcomes leave the newest twenty, in order,
    and the newest instant; a claim inside the interval is refused and one after it granted; a
    probe outcome lands in the probe ring and not the live one.

    Delete this and the ring function and the claim are only ever compiled, and the first time
    either runs is on an install."""
    sql(database, "TRUNCATE ops.provider_health")
    db = engine(database)
    sessions = async_sessionmaker(db, expire_on_commit=False)
    health = SessionHealth(sessions)

    async def through() -> tuple[bool, bool, bool]:
        for n in range(LIVE_RING_CAP + 5):
            await health.observed(
                deployment_id="anthropic-main",
                provider="anthropic",
                ok=n % 2 == 0,
                at=AT + timedelta(seconds=n),
            )
        grants = []
        for at in (AT, AT + timedelta(seconds=30), AT + timedelta(seconds=61)):
            async with sessions() as session:
                found = await session.execute(
                    probe_claimed(
                        "anthropic-main", "anthropic", at=at, interval=timedelta(seconds=60)
                    )
                )
                grants.append(found.first() is not None)
                await session.commit()
        async with sessions() as session:
            await session.execute(probe_observed("anthropic-main", ok=False, at=AT))
            await session.commit()
        await db.dispose()
        return grants[0], grants[1], grants[2]

    first, inside, after = run(through)

    ((live, probe, last_live),) = sql(
        database, "SELECT live, probe, last_live_at FROM ops.provider_health"
    )
    assert len(live) == LIVE_RING_CAP
    assert live[0]["at"] == (AT + timedelta(seconds=5)).isoformat()
    assert live[-1]["at"] == (AT + timedelta(seconds=LIVE_RING_CAP + 4)).isoformat()
    assert last_live == AT + timedelta(seconds=LIVE_RING_CAP + 4)
    assert (first, inside, after) == (True, False, True)
    assert probe == [{"ok": False, "at": AT.isoformat()}]


def test_the_ladder_reads_the_tiers_constraints_and_rings_and_an_alert_is_kept(
    database: str,
) -> None:
    """**M5.2.2, M5.5.1 and M5.4.8 against a server.** A tier row and one carrying a key the router
    does not read, a live constraint and a retired one, and a ring, all read by the ladder in one
    session; an alert written and read back.

    Delete this and the executor's inputs are only ever built by hand in tests, and a column
    renamed in a migration reaches the router as an unreadable ladder on an install."""
    sql(
        database,
        "TRUNCATE ops.routing_tier, ops.residency_constraint, ops.provider_health, "
        "ops.chain_depth_alert",
    )
    sql(
        database,
        "INSERT INTO ops.routing_tier (tier, context_window, rules) VALUES "
        "('main', 50000, '{\"escalation_headroom\": 0.5}'::jsonb), "
        "('heavy', 90000, '{\"predicate\": \"payroll\"}'::jsonb)",
    )
    sql(
        database,
        "INSERT INTO ops.residency_constraint (scope, allowed_regions, created_by) VALUES "
        '(\'{"clauses": [{"field": "department", "op": "eq", "value": "finance"}]}\''
        "::jsonb, '[\"eu-west-1\"]'::jsonb, 'u_admin')",
    )
    sql(
        database,
        "INSERT INTO ops.residency_constraint (scope, on_prem_only, created_by, deleted_at) "
        "VALUES ('{\"clauses\": []}'::jsonb, true, 'u_admin', now())",
    )
    sql(
        database,
        "INSERT INTO ops.provider_health (deployment_id, provider, probe, last_probe_at) VALUES "
        "('anthropic-main', 'anthropic', %s::jsonb, %s)",
        f'[{{"ok": false, "at": "{AT.isoformat()}"}}]',
        AT,
    )
    db = engine(database)
    sessions = async_sessionmaker(db, expire_on_commit=False)

    async def through() -> tuple[Any, Any]:
        state = await SessionLadder(sessions).current(AT)
        await SessionDepthAlerts(sessions).raised(
            DepthAlert(
                level=AlertLevel.WARNING,
                tier=Tier.MAIN,
                depth=2,
                served_by="moonshot-main",
                reason="tier main answered on rung 2 rather than its primary",
            ),
            trace_id="b" * 32,
            at=AT,
        )
        async with sessions() as session:
            alerts = (await session.execute(recent_alerts(AT - timedelta(hours=1)))).scalars().all()
        await db.dispose()
        return state, alerts

    state, alerts = run(through)

    assert [(one.tier, one.context_window, one.headroom) for one in state.tiers] == [
        (Tier.MAIN, 50_000, 0.5)
    ]
    (constraint,) = state.residency
    assert constraint.requirement.allowed_regions == frozenset({"eu-west-1"})
    (ring,) = state.rings
    assert (ring.deployment_id, [p.ok for p in ring.probe], ring.last_probe_at) == (
        "anthropic-main",
        [False],
        AT,
    )
    (alert,) = alerts
    assert (alert.level, alert.tier, alert.depth, alert.served_by) == (
        "warning",
        "main",
        2,
        "moonshot-main",
    )
