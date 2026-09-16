"""The model driver as the application holds it: the statements, the stores and the wiring.

The statements are compiled against PostgreSQL's dialect and asserted on their structure. The
stores are then run against a scratch database built from the models, which is skipped where no
server is named and which CI always runs.

Task ids: M27.8.8, M5.3.4, M5.1.2
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.core.lane import Lane
from brain.models.driver import DriverMessage, Role
from brain.models.metering import Meter
from brain.models.routing import NoCompliantRoute, Tier
from brain.models.wire import LOCAL_PROVIDER, PROVIDER_WIRES
from brain.ops.model_service import (
    A_SWITCH_NOBODY_COULD_READ_IS_OFF,
    KNOWN_PROVIDERS,
    MAX_RUNGS,
    NoAttempts,
    NoLadder,
    SessionAttempts,
    SessionLadder,
    attempt_finished,
    drivers_for,
    held_providers,
    live_rungs,
    model_service_at_start,
    provider_key,
    recent_attempts,
    switch_provider,
    switch_states,
    switched_off_in,
)
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.setting_store import SettingState
from brain.tables.config import SettingType
from tests.fixtures.scratch_postgres import engine, modelled, run, sql

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
T0 = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
TRACE = "c" * 32


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=DIALECT, compile_kwargs={"literal_binds": False})).replace(
        "\n", " "
    )


def state(value: object, value_type: SettingType = SettingType.BOOLEAN) -> SettingState:
    return SettingState(
        key="provider.x", value_type=value_type.value, value=value, updated_by="u", updated_at=T0
    )


# ----------------------------------------------------------------------- the statements


def test_the_ladder_is_the_live_rungs_in_chain_order_and_bounded() -> None:
    """Delete this and a retired rung can be planned from on a database restored without its
    policy, or the ladder can be read in whatever order the planner chose."""
    text = compiled(live_rungs())
    assert "ops.routing_rung.deleted_at IS NULL" in text
    assert "ORDER BY ops.routing_rung.tier, ops.routing_rung.position" in text
    assert live_rungs()._limit == MAX_RUNGS


def test_recent_attempts_are_finished_ones_joined_to_their_rungs_deployment() -> None:
    """Delete this and an attempt still in flight is replayed as evidence, or health is keyed by a
    rung id the screen cannot match to a deployment."""
    text = compiled(recent_attempts(T0))
    assert "JOIN ops.routing_rung ON ops.routing_rung.id = ops.model_attempt.rung_id" in text
    assert "ops.model_attempt.finished_at IS NOT NULL" in text
    assert "ops.model_attempt.finished_at >= " in text
    assert text.startswith("SELECT ops.routing_rung.deployment_id,")


def test_an_attempt_is_finished_by_its_id_and_never_by_its_trace() -> None:
    """A caller may propose its own trace id. Delete this and a finish matched on the trace and the
    sequence overwrites an earlier request's attempt with this one's outcome."""
    token = str(uuid.uuid4())
    text = compiled(attempt_finished(token, T0, "ok", None))
    where = text.split("WHERE", 1)[1]
    assert "ops.model_attempt.id = " in where
    assert "trace_id" not in where
    assert "sequence" not in where


def test_only_the_json_false_switches_a_provider_off() -> None:
    """Delete this and a string written at a prompt, which is truthy, switches a provider off or
    on depending on which way somebody wrote the check."""
    states = {
        "anthropic": state(False),
        "openai": state(True),
        "moonshot": state("false", SettingType.STRING),
        "local": state(0, SettingType.INTEGER),
    }
    assert switched_off_in(states) == frozenset({"anthropic"})


def test_the_known_providers_are_the_key_slots_and_the_local_server() -> None:
    """Held against the slot table rather than restated. Delete this and a provider added to the
    slots cannot be switched or checked from the console."""
    assert (*(one.slug for one in PROVIDER_SLOTS), LOCAL_PROVIDER) == KNOWN_PROVIDERS
    assert provider_key("anthropic") == "provider.anthropic"


def test_a_key_held_is_read_from_the_environments_names_and_a_blank_is_not_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the executor can believe it holds a key the environment sets to nothing,
    and send every question to a provider as an unauthenticated request."""
    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    anthropic = next(one for one in PROVIDER_SLOTS if one.slug == "anthropic")
    moonshot = next(one for one in PROVIDER_SLOTS if one.slug == "moonshot")
    monkeypatch.setenv(anthropic.env_var, "sk-value")
    monkeypatch.setenv(moonshot.env_var, "")

    assert held_providers() == frozenset({"anthropic"})


def test_a_driver_is_built_for_every_hosted_provider_and_the_local_one_at_a_usable_address() -> (
    None
):
    """A hosted driver exists whether or not a key does, because a key can arrive while the
    process runs; the local one exists only where `endpoint_refusals` has nothing to say.

    Delete this and either a key saved from the console needs a restart to be used, or a rung
    naming the local server dials an address that is not an origin."""
    with httpx.Client() as client:
        usable = drivers_for(client, inference_address="http://inference-server:8080")
        unusable = drivers_for(client, inference_address="inference-server/path?x=1")

    assert set(usable) == {*PROVIDER_WIRES, LOCAL_PROVIDER}
    assert set(unusable) == set(PROVIDER_WIRES)


# -------------------------------------------------------------------------- the stores


class Refusing(AsyncSession):
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        msg = "the database is down"
        raise ConnectionError(msg)


def test_a_ladder_that_cannot_be_read_is_no_rungs_and_every_provider_switched_off() -> None:
    """See `A_SWITCH_NOBODY_COULD_READ_IS_OFF`. Delete this and a database outage reads as nobody
    having switched anything off, which sends questions to a provider somebody took out."""
    found = run(lambda: SessionLadder(async_sessionmaker(class_=Refusing)).current(T0))

    assert found.rungs == ()
    assert found.switched_off == frozenset(KNOWN_PROVIDERS)
    assert "off" in A_SWITCH_NOBODY_COULD_READ_IS_OFF


def test_an_attempt_row_that_cannot_be_written_does_not_stop_the_call() -> None:
    """Delete this and a database hiccup during a model call turns an answered question into a
    fault the asker sees."""
    attempts = SessionAttempts(async_sessionmaker(class_=Refusing))

    token = run(
        lambda: attempts.started(trace_id=TRACE, rung_id=str(uuid.uuid4()), sequence=0, at=T0)
    )
    run(lambda: attempts.finished(token, at=T0, outcome="ok", status=None))

    assert token == ""


def test_a_process_with_no_database_calls_nothing_and_says_no_model_is_configured() -> None:
    """Delete this and a process started without a database can build an executor that fails with
    an attribute error on the first model call rather than refusing in words."""
    with httpx.Client() as client:
        service = model_service_at_start(None, client=client)
        assert isinstance(service.calls._ladder, NoLadder)
        assert isinstance(service.calls._attempts, NoAttempts)
        with pytest.raises(NoCompliantRoute):
            run(
                lambda: service.calls.complete(
                    (DriverMessage(role=Role.USER, content="hello"),),
                    tier=Tier.MAIN,
                    lane=Lane.ANSWER,
                    meter=Meter(),
                    trace_id=TRACE,
                )
            )


def test_switching_an_unknown_provider_is_refused_before_anything_is_written() -> None:
    """Delete this and a switch row for a provider nothing reads can be written from the console."""
    with pytest.raises(ValueError, match="not a provider"):
        run(lambda: switch_provider(Refusing(), "somebody_else", on=False, by="u_admin"))


# ------------------------------------------------------------------ against a database

TABLES = ("ops.routing_rung", "ops.model_attempt", "ops.setting")


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with modelled("brain_test_model_service", TABLES) as url:
        yield url


def _rung(url: str, *, deployment: str, provider: str, tier: str, position: int) -> str:
    rung_id = str(uuid.uuid4())
    sql(
        url,
        "INSERT INTO ops.routing_rung (id, tier, scope, position, role, deployment_id, provider, "
        "model, attempts, timeout_seconds, max_concurrency, enabled) VALUES "
        "(%s, %s, '{}'::jsonb, %s, 'primary', %s, %s, %s, 1, 12.5, 4, true)",
        rung_id,
        tier,
        position,
        deployment,
        provider,
        f"{provider}-model",
    )
    return rung_id


def test_the_stores_read_the_ladder_write_attempts_by_id_and_keep_a_switch(database: str) -> None:
    """One pass through every statement against a real server: two rungs, a retired one, an
    attempt started and finished, a second request reusing the trace and sequence, and a switch.

    Delete this and the statements are only ever compiled, and the first time one runs is on an
    install, which is where `brain.routing_routes` says its own write was first exercised."""
    sql(database, "TRUNCATE ops.model_attempt, ops.routing_rung, ops.setting")
    first = _rung(
        database, deployment="anthropic-main", provider="anthropic", tier="main", position=0
    )
    _rung(database, deployment="moonshot-main", provider="moonshot", tier="main", position=1)
    retired = _rung(database, deployment="old-main", provider="openai", tier="main", position=2)
    sql(database, "UPDATE ops.routing_rung SET deleted_at = now() WHERE id = %s", retired)

    db = engine(database)
    sessions = async_sessionmaker(db, expire_on_commit=False)
    attempts = SessionAttempts(sessions)
    now = datetime.now(UTC)

    async def through() -> tuple[Any, Any]:
        token = await attempts.started(trace_id=TRACE, rung_id=first, sequence=0, at=now)
        await attempts.finished(
            token, at=now + timedelta(seconds=1), outcome="timeout", status=None
        )
        # A second request under the same caller-proposed trace: refused by the unique index,
        # so its finish must not reach the first row.
        again = await attempts.started(trace_id=TRACE, rung_id=first, sequence=0, at=now)
        await attempts.finished(again, at=now + timedelta(seconds=2), outcome="ok", status=None)
        async with sessions() as session:
            await switch_provider(session, "moonshot", on=False, by="u_admin")
            await session.commit()
        async with sessions() as session:
            switches = await switch_states(session)
        current = await SessionLadder(sessions).current(now + timedelta(seconds=5))
        await db.dispose()
        return switches, (token, again, current)

    switches, (token, again, current) = run(through)

    assert token != ""
    assert again == ""
    assert [one.deployment_id for one in current.rungs] == ["anthropic-main", "moonshot-main"]
    assert current.rungs[0].timeout_seconds == 12.5
    assert current.switched_off == frozenset({"moonshot"})
    assert switches["moonshot"].updated_by == "u_admin"
    assert [(one.deployment_id, one.outcome) for one in current.attempts] == [
        ("anthropic-main", "timeout")
    ]
    assert sql(database, "SELECT outcome FROM ops.model_attempt") == [("timeout",)]
