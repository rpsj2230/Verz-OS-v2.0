"""Switching an agent's channels over HTTP, on PostgreSQL.

Driven through the real application with signed-in people and the application role, so `0159`'s
policies and its ledger trigger are the ones an install has, and the answer route's own channel
reader is asked which agents a question on each channel keeps.

Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

import httpx
import pytest

from brain.agent_channel_routes import SWITCHING_NEEDS_THE_CONNECTOR_ROLE, router
from brain.agent_roster import agent_channels_for, agent_roster_for
from brain.agents.channel_switches import (
    ALREADY_ON,
    NOT_A_CHANNEL_HERE,
    NOT_REACHABLE,
    answering_on,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

AGENT = "sales_desk"
HIDDEN = "private_desk"
PATH = f"{API_PREFIX}/agents/{AGENT}/channels"

AGENT_ROW = (
    "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
    " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
    " created_by) VALUES (%s, 'Desk', 'Answer briefly.', 'main', %s, %s, NULL,"
    " '{\"clauses\": []}', '{read:client}', '{}', '{}', 'none', 'u_admin')"
)


def everywhere(*capabilities: str) -> tuple[Grant, ...]:
    return tuple(
        Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in capabilities
    )


#: `u_admin` holds the connector role; `u_prefix` sees the company's agents and holds no role.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": everywhere("admin:connector", "read:client"),
    "u_prefix": everywhere("read:client"),
}


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_channels_{uuid.uuid4().hex[:8]}") as url:
        sql(url, AGENT_ROW, AGENT, "company", "u_steward")
        sql(url, AGENT_ROW, HIDDEN, "personal", "u_somebody_else")
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient, Any], Awaitable[T]]) -> T:
    """The channel routes over this database as the application role, and the answer route's
    readers over the same sessions. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = sessions
            roster, channels = agent_roster_for(sessions), agent_channels_for(sessions)
            assert roster is not None and channels is not None

            async def answering(channel: Channel) -> list[str]:
                records = await roster()
                on = await channels([one.agent_id for one in records])
                return [one.agent_id for one in answering_on(records, on, channel)]

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client, answering)
        finally:
            await built.dispose()

    return run(go)


def press(channel: str, on: bool) -> dict[str, Any]:
    return {"channel": channel, "on": on}


def test_an_agents_channels_are_switched_by_the_connector_role_and_a_question_keeps_only_those(
    database: str,
) -> None:
    """**M39.2.4.1 on PostgreSQL.** An agent nothing switched on answers nowhere and its page says
    so; a member sees where it answers and may not switch, told which role would let them; a channel
    with no row and a switch to the state already held are refused in one sentence each; the web
    page switched on makes the answer route keep the agent on the web page and on no chat; switched
    off, it is gone again; and every switch is one `compose_change` entry naming who and which way.
    An agent the reader may not see is the 404 an agent that does not exist is.

    Delete this and a switch can answer 200 over a row the table refuses, a member can switch an
    agent on, or the page says an agent answers while the answer route keeps it out."""

    async def act(client: httpx.AsyncClient, answering: Any) -> Any:
        said: dict[str, Any] = {}
        said["before"] = (await client.get(PATH, headers=headers("u_prefix"))).json()
        said["before_web"] = await answering(Channel.CONSOLE)
        said["refused"] = await client.post(
            PATH, json=press("console", True), headers=headers("u_prefix")
        )
        said["no_row"] = await client.post(
            PATH, json=press("api", True), headers=headers("u_admin")
        )
        said["on"] = await client.post(
            PATH, json=press("console", True), headers=headers("u_admin")
        )
        said["on_web"] = await answering(Channel.CONSOLE)
        said["on_lark"] = await answering(Channel.LARK)
        said["again"] = await client.post(
            PATH, json=press("console", True), headers=headers("u_admin")
        )
        said["off"] = await client.post(
            PATH, json=press("console", False), headers=headers("u_admin")
        )
        said["off_web"] = await answering(Channel.CONSOLE)
        hidden = f"{API_PREFIX}/agents/{HIDDEN}/channels"
        nobody = f"{API_PREFIX}/agents/no_such_desk/channels"
        said["hidden"] = (await client.get(hidden, headers=headers("u_prefix"))).status_code
        said["nobody"] = (await client.get(nobody, headers=headers("u_prefix"))).status_code
        return said

    said = pressed(database, act)
    before = said["before"]
    assert before["channels"][0] == {
        "channel": "console",
        "on": False,
        "profile": None,
        "group_installable": False,
    }
    assert (before["reachable"], before["unreachable"], before["may_switch"]) == (
        False,
        NOT_REACHABLE,
        False,
    )
    assert said["before_web"] == []
    assert said["refused"].status_code == 403
    assert said["refused"].json()["message"] == SWITCHING_NEEDS_THE_CONNECTOR_ROLE
    assert said["no_row"].status_code == 409
    assert said["no_row"].json()["message"] == NOT_A_CHANNEL_HERE
    on = said["on"].json()
    assert (on["reachable"], on["unreachable"], on["channels"][0]["on"]) == (True, None, True)
    assert said["on_web"] == [AGENT]
    assert said["on_lark"] == []
    assert said["again"].json()["message"] == ALREADY_ON
    assert said["off"].json()["unreachable"] == NOT_REACHABLE
    assert said["off_web"] == []
    assert said["hidden"] == said["nobody"] == 404
    ledgered = [one for one in entries(database, "compose_change") if one.actor_id == "u_admin"]
    assert [
        (one.subject, dict(one.details)["part"], dict(one.details)["direction"]) for one in ledgered
    ] == [
        (f"agent:{AGENT}", "channels", "attached"),
        (f"agent:{AGENT}", "channels", "detached"),
    ]
