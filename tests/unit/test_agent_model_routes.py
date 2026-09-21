"""An agent's pinned provider and model, set from the console and read back into its record.

Driven through the real application with the provider routes' estate, so the pin is checked
against the ladder the executor plans from.

Task ids: M5.7.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import record_of
from brain.agents.install_store import agent_values
from brain.app import Settings, create_app
from brain.models.registry import ModelPin
from brain.tables.agent import AgentRow
from tests.unit.test_provider_routes import Estate, Ledger, Questions, _service, _wiring, call

PIN = "/api/v1/agents/sales_helper/model-pin"

_WRITES: list[dict[str, Any]] = []
_AGENTS: set[str] = {"sales_helper"}


class _Found:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class PinSession(AsyncSession):
    """Answers the pin's UPDATE with the agent's id when that agent exists, and records it."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        params = dict(statement.compile().params)
        _WRITES.append(params)
        agent = next((v for k, v in params.items() if k.startswith("id_")), None)
        return _Found(agent if agent in _AGENTS else None)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    _WRITES.clear()
    estate = Estate()
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=PinSession)
        app.state.models.close()
        app.state.models = _service(estate)
        app.state.request_recorders = (Questions(), Ledger())
        yield c


def test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent(
    client: TestClient,
) -> None:
    """M5.7.3: an administrator may pin a specific provider and model.

    Delete this and the pin has no way in from the console."""
    response = call(
        client, "PUT", "u_wide", PIN, {"provider": "moonshot", "model": "moonshot-model"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "agent_id": "sales_helper",
        "provider": "moonshot",
        "model": "moonshot-model",
    }
    (written,) = _WRITES
    assert written["model_pin_provider"] == "moonshot"
    assert written["model_pin_model"] == "moonshot-model"


def test_a_pin_naming_a_model_no_rung_serves_is_refused_with_the_reason(
    client: TestClient,
) -> None:
    """`A_PIN_CHOOSES_AMONG_THE_LADDERS_MODELS`. Delete this and a pin is accepted that the
    executor will pass over on every question, with the screen saying it took effect."""
    response = call(client, "PUT", "u_wide", PIN, {"provider": "moonshot", "model": "kimi-k9"})

    assert response.status_code == 422
    assert "Routing screen" in response.text
    assert _WRITES == []


def test_a_pin_is_cleared_back_to_the_tier_and_half_a_pin_is_refused(client: TestClient) -> None:
    """Both null goes back to the tier; one without the other names nothing to call.

    Delete this and a pin can never be removed, or a provider can be pinned with no model."""
    cleared = call(client, "PUT", "u_wide", PIN, {"provider": None, "model": None})
    half = call(client, "PUT", "u_wide", PIN, {"provider": "moonshot", "model": None})

    assert cleared.status_code == 200
    assert _WRITES[0]["model_pin_provider"] is None
    assert half.status_code == 422


def test_pinning_needs_the_matrix_write_over_everything(client: TestClient) -> None:
    """It decides where every question to the agent goes first, whoever asks.

    Delete this and a reader of the Models screen, or a department's editor, can move an agent's
    questions to another provider."""
    for pid in ("u_narrow", "u_elsewhere", "u_none"):
        response = call(
            client, "PUT", pid, PIN, {"provider": "moonshot", "model": "moonshot-model"}
        )
        assert response.status_code == 404, pid
    assert _WRITES == []


def test_a_pin_for_an_agent_that_is_not_there_is_the_one_refusal(client: TestClient) -> None:
    """Delete this and the route answers 200 for an agent nobody configured."""
    response = call(
        client,
        "PUT",
        "u_wide",
        "/api/v1/agents/nobody_here/model-pin",
        {"provider": "moonshot", "model": "moonshot-model"},
    )

    assert response.status_code == 404


def test_the_stored_pin_reads_back_into_the_agents_record_and_is_written_back_the_same() -> None:
    """The row and the record carry the pin both ways. Delete this and a pin set on the console
    never reaches the record the model lane hands the executor."""
    row = AgentRow(
        id="sales_helper",
        display_name="Sales helper",
        persona="Helps with sales.",
        tier="main",
        visibility="company",
        owner_id="u_owner",
        department=None,
        scope={"clauses": []},
        capabilities=[],
        allowed_tools=[],
        required_tools=[],
        max_side_effect="none",
        created_by="u_owner",
        disabled_at=None,
        archived_at=None,
        model_pin_provider="moonshot",
        model_pin_model="kimi-k2",
    )

    record = record_of(row)

    assert record is not None
    assert record.model_pin == ModelPin(provider="moonshot", model="kimi-k2")
    values = agent_values(record)
    assert (values["model_pin_provider"], values["model_pin_model"]) == ("moonshot", "kimi-k2")
