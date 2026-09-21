"""A tier's numbers and a residency constraint, set from the Models and health screen.

Driven through the real application with the estate `tests.unit.test_provider_routes` builds and a
session that records every write, so what is written, what is refused and what reaches the answer
are inspected without a server.

Task ids: M5.2.2, M5.5.1, M5.4.3, M5.4.8
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.models.calls import LadderState
from brain.models.evidence import RingEntry, StoredRings
from brain.models.routing import Tier
from brain.models.tier_rules import HEADROOM_KEY, TierRule
from tests.unit.test_provider_routes import (
    PROVIDERS,
    Estate,
    Ledger,
    Questions,
    _service,
    _wiring,
    call,
)

TIERS = f"{API_PREFIX}/models/tiers"
RESIDENCY = f"{API_PREFIX}/models/residency"
FINANCE = {"clauses": [{"field": "department", "op": "eq", "value": "finance"}]}
AT = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)


@dataclass
class HealthEstate(Estate):
    """The provider routes' estate, with a tier row, a stored ring and a log of every write."""

    tiers: tuple[TierRule, ...] = ()
    rings: tuple[StoredRings, ...] = ()
    writes: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    async def current(self, now: datetime) -> LadderState:
        state = await super().current(now)
        return LadderState(
            rungs=state.rungs,
            switched_off=state.switched_off,
            attempts=state.attempts,
            tiers=self.tiers,
            rings=self.rings,
        )


_HEALTH = HealthEstate()


class _Nothing:
    def all(self) -> list[Any]:
        return []

    def scalars(self) -> _Nothing:
        return self

    def scalar_one_or_none(self) -> None:
        return None


class RecordingSession(AsyncSession):
    """Records every INSERT and UPDATE; answers every read with nothing."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        table = getattr(getattr(statement, "table", None), "fullname", "")
        if getattr(statement, "is_insert", False) or getattr(statement, "is_update", False):
            verb = "insert" if statement.is_insert else "update"
            _HEALTH.writes.append((verb, table, dict(statement.compile().params)))
        return _Nothing()

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def health() -> Iterator[HealthEstate]:
    global _HEALTH
    _HEALTH = HealthEstate()
    yield _HEALTH


@pytest.fixture
def client(health: HealthEstate) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=RecordingSession)
        app.state.models.close()
        app.state.models = _service(health)
        app.state.request_recorders = (Questions(), Ledger())
        yield c


def _writes(health: HealthEstate, table: str) -> list[tuple[str, dict[str, Any]]]:
    return [(verb, row) for verb, name, row in health.writes if name == table]


# ------------------------------------------------------------------------ the tier (M5.2.2)
def test_a_tier_rule_is_written_as_the_window_and_only_the_keys_the_router_reads(
    client: TestClient, health: HealthEstate
) -> None:
    """**The console half of M5.2.2.** Setting main's window and headroom inserts one
    `ops.routing_tier` row whose rule set holds the headroom and nothing else.

    Delete this and the table the router now reads has no writer anybody can reach."""
    response = call(
        client,
        "PUT",
        "u_wide",
        f"{TIERS}/main",
        {"context_window": 50_000, "escalation_headroom": 0.5},
    )

    assert response.status_code == 200, response.text
    ((verb, row),) = _writes(health, "ops.routing_tier")
    assert verb == "insert"
    assert row["tier"] == "main"
    assert row["context_window"] == 50_000
    assert row["rules"] == {HEADROOM_KEY: 0.5}


@pytest.mark.parametrize(
    ("tier", "body"),
    [
        ("none", {"context_window": 1_000}),
        ("mian", {"context_window": 1_000}),
        ("main", {"context_window": 0}),
        ("main", {"context_window": 1_000, "escalation_headroom": 2.0}),
    ],
)
def test_a_tier_rule_the_router_would_not_use_is_refused_and_writes_nothing(
    client: TestClient, health: HealthEstate, tier: str, body: dict[str, Any]
) -> None:
    """Delete this and a row the router leaves out, or one widening the fast lane, could be saved
    and shown as the setting in force."""
    response = call(client, "PUT", "u_wide", f"{TIERS}/{tier}", body)

    assert response.status_code == 422
    assert health.writes == []


def test_a_reset_retires_the_row_so_the_tier_runs_at_the_product_default(
    client: TestClient, health: HealthEstate
) -> None:
    """Delete this and a tier row, once written, could never be taken back to the numbers the
    product shipped and tested."""
    response = call(client, "POST", "u_wide", f"{TIERS}/heavy/reset")

    assert response.status_code == 200, response.text
    ((verb, row),) = _writes(health, "ops.routing_tier")
    assert verb == "update"
    assert row["tier_1"] == "heavy"


def test_the_view_says_which_tiers_a_row_governs_and_shows_the_numbers_in_force(
    client: TestClient, health: HealthEstate
) -> None:
    """Delete this and the screen could draw the compiled default as a setting somebody made, or
    hide the headroom the router is using."""
    health.tiers = (TierRule(tier=Tier.MAIN, context_window=50_000, headroom=0.5),)

    body = call(client, "GET", "u_narrow", PROVIDERS).json()

    by_tier = {one["tier"]: one for one in body["tiers"]}
    assert list(by_tier) == ["small", "main", "heavy"]
    assert by_tier["main"] == {
        "tier": "main",
        "context_window": 50_000,
        "escalation_headroom": 0.5,
        "configured": True,
    }
    assert by_tier["small"]["configured"] is False


# ------------------------------------------------------------------- residency (M5.5.1)
def test_a_residency_constraint_is_written_with_its_scope_and_regions(
    client: TestClient, health: HealthEstate
) -> None:
    """**The console half of M5.5.1.** The scope is stored in the grant tables' shape and the
    regions as given, trimmed, with who wrote it.

    Delete this and a constraint could be stored in a shape the router cannot read back."""
    response = call(
        client,
        "POST",
        "u_wide",
        RESIDENCY,
        {"scope": FINANCE, "allowed_regions": [" eu-west-1 "], "note": "finance stays in the EU"},
    )

    assert response.status_code == 200, response.text
    ((verb, row),) = _writes(health, "ops.residency_constraint")
    assert verb == "insert"
    assert row["scope"] == FINANCE
    assert row["allowed_regions"] == ["eu-west-1"]
    assert row["on_prem_only"] is False
    assert row["created_by"] == "u_wide"


@pytest.mark.parametrize(
    "body",
    [
        {"scope": FINANCE},
        {"scope": FINANCE, "allowed_regions": []},
        {"scope": FINANCE, "allowed_regions": ["global"]},
        {"scope": {"clauses": [{"field": "department", "op": "nope"}]}, "on_prem_only": True},
    ],
)
def test_a_constraint_that_would_mislead_is_refused_and_writes_nothing(
    client: TestClient, health: HealthEstate, body: dict[str, Any]
) -> None:
    """Delete this and a constraint demanding nothing, refusing everything, promising `global` or
    attached to a scope no grant could hold could be saved and shown as a policy."""
    assert call(client, "POST", "u_wide", RESIDENCY, body).status_code == 422
    assert health.writes == []


def test_retiring_a_constraint_marks_it_retired_and_deletes_nothing(
    client: TestClient, health: HealthEstate
) -> None:
    """Delete this and the constraint in force when a question was refused could vanish."""
    one = "00000000-0000-4000-8000-000000000001"

    response = call(client, "POST", "u_wide", f"{RESIDENCY}/{one}/retire")

    assert response.status_code == 200, response.text
    ((verb, _),) = _writes(health, "ops.residency_constraint")
    assert verb == "update"


@pytest.mark.parametrize("pid", ["u_narrow", "u_elsewhere", "u_none"])
def test_every_routing_setting_needs_the_matrix_write_held_over_everything(
    client: TestClient, health: HealthEstate, pid: str
) -> None:
    """`ROUTING_SETTINGS_ARE_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION`. A reader, a department's
    editor and nobody are each refused identically and nothing is written.

    Delete this and somebody scoped to one department could decide which pool, or which region,
    every department's questions go to."""
    one = "00000000-0000-4000-8000-000000000001"
    for method, path, body in (
        ("PUT", f"{TIERS}/main", {"context_window": 50_000}),
        ("POST", f"{TIERS}/main/reset", None),
        ("POST", RESIDENCY, {"scope": FINANCE, "on_prem_only": True}),
        ("POST", f"{RESIDENCY}/{one}/retire", None),
    ):
        assert call(client, method, pid, path, body).status_code == 404, (pid, path)
    assert health.writes == []


# -------------------------------------------------------- what the screen shows (M5.4.3)
def test_each_rung_shows_its_stored_probes_and_when_it_was_last_probed_and_called(
    client: TestClient, health: HealthEstate
) -> None:
    """Delete this and the probe ring the worker writes reaches no screen, so an idle rung the
    prober found dead looks exactly like one nobody has checked."""
    first = health.rungs[0]
    health.rings = (
        StoredRings(
            deployment_id=first.deployment_id,
            provider=first.provider,
            probe=(RingEntry(ok=True, at=AT), RingEntry(ok=False, at=AT)),
            last_probe_at=AT,
            last_live_at=AT,
        ),
    )

    body = call(client, "GET", "u_narrow", PROVIDERS).json()

    row = next(one for one in body["rungs"] if one["deployment_id"] == first.deployment_id)
    assert (row["probes_seen"], row["probes_failed"]) == (2, 1)
    assert row["last_probe_at"].startswith("2999-01-01T12:00")
    assert body["depth_alerts"] == []
    assert body["residency"] == []
