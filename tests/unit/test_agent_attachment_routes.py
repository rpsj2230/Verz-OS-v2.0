"""Attaching and detaching an agent's tools and connectors over HTTP, on PostgreSQL.

Driven through the real application with signed-in people, the application role and a real tool
registry, so the ceiling check, `0160`'s policies and its ledger trigger are the ones an install
has, and the answer route's own roster reader is asked what a run would now be handed.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

import httpx
import pytest

from brain.agent_attachment_routes import CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE, router
from brain.agent_roster import agent_roster_for
from brain.agents.attachments import CANNOT_BE_ATTACHED
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Scope
from brain.session import make_session_factory
from brain.tools.registry import ToolRegistry
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

AGENT = "sales_desk"
PATH = f"{API_PREFIX}/agents/{AGENT}/attachments"


class Deal(Entity):
    stage: str = ""


def a_handler() -> TypedResult[Deal]:
    return TypedResult[Deal]()


def tool(name: str, capability: str, effect: SideEffect = SideEffect.NONE) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"The {name} tool",
        entity=name.split(".", 1)[0],
        required_capability=capability,
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
        source=name.split(".", 1)[0],
    )


def registry() -> ToolRegistry:
    made = ToolRegistry()
    for one in (
        tool("crm.read_client", "read:client"),
        tool("crm.read_deal", "read:deal"),
        tool("crm.update_deal", "write:deal.stage", SideEffect.WRITE),
        tool("desk.read_ticket", "read:ticket"),
    ):
        made.register(one, a_handler)
    return made


def everywhere(*capabilities: Capability | str) -> tuple[Grant, ...]:
    return tuple(
        Grant(
            capability=one if isinstance(one, Capability) else Capability(value=one),
            scope=Scope.unrestricted(),
        )
        for one in capabilities
    )


SETTINGS_READ = (tab(Tab.SETTINGS).read.requires, *(plane_capability(one) for one in Plane))
REACHES = ("read:client", "read:deal", "write:deal.stage", "read:ticket")

#: `u_admin` holds the tool and connector roles and reaches every tool; `u_prefix` reads the
#: Settings tab and every tool and holds neither role.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": everywhere(*SETTINGS_READ, "admin:tool", "admin:connector", *REACHES),
    "u_prefix": everywhere(*SETTINGS_READ, *REACHES),
}


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_attachments_{uuid.uuid4().hex[:8]}") as url:
        sql(
            url,
            "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
            " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
            " created_by) VALUES (%s, 'Sales desk', 'Answer briefly.', 'main', 'company',"
            " 'u_narrow', NULL, '{\"clauses\": []}', '{read:client,read:deal,write:deal.stage}',"
            " '{crm.read_client}', '{}', 'none', 'u_admin')",
            AGENT,
        )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient, Any], Awaitable[T]]) -> T:
    """The attachment routes over this database as the application role, with a real registry,
    and the answer route's roster reader over the same sessions. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = sessions
            app.state.tools = registry()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client, agent_roster_for(sessions))
        finally:
            await built.dispose()

    return run(go)


def press(part: str, reference: str, attached: bool) -> dict[str, Any]:
    return {"part": part, "reference": reference, "attached": attached}


def test_tools_and_connectors_are_attached_within_the_ceiling_and_a_run_carries_only_those(
    database: str,
) -> None:
    """**M39.8.6, M39.2.1.2 and M39.1.1.3 on PostgreSQL.** The reader is offered only what the
    ceiling and their reach admit; without the tool role a press is refused naming it; a tool
    above the ceiling is refused in one sentence; a tool, then a connector's tools, are attached and
    detached; the answer route's roster reader hands a run exactly the tools the agent carries after
    each; and every press is one `compose_change` entry naming who, what and which way.

    Delete this and a press can answer 200 over a row the table refuses, a tool the ceiling cannot
    run can be attached, or a detach changes the page and not what a run is handed."""

    async def act(client: httpx.AsyncClient, roster: Any) -> Any:
        said: dict[str, Any] = {}
        said["offered"] = (await client.get(PATH, headers=headers("u_admin"))).json()
        said["refused"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", True), headers=headers("u_prefix")
        )
        said["above"] = await client.post(
            PATH, json=press("tool", "crm.update_deal", True), headers=headers("u_admin")
        )
        said["attached"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", True), headers=headers("u_admin")
        )
        said["after_attach"] = {one.agent_id: one for one in await roster()}[AGENT]
        said["connector_off"] = await client.post(
            PATH, json=press("connector", "crm", False), headers=headers("u_admin")
        )
        said["after_off"] = {one.agent_id: one for one in await roster()}[AGENT]
        said["connector_on"] = await client.post(
            PATH, json=press("connector", "crm", True), headers=headers("u_admin")
        )
        said["tool_off"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", False), headers=headers("u_admin")
        )
        said["final"] = {one.agent_id: one for one in await roster()}[AGENT]
        return said

    said = pressed(database, act)
    assert [one["name"] for one in said["offered"]["tools"]] == ["crm.read_deal"]
    assert said["offered"]["connectors"] == ["crm"]
    assert said["refused"].status_code == 403
    assert said["refused"].json()["message"] == CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE
    assert said["above"].status_code == 409
    assert said["above"].json()["message"] == CANNOT_BE_ATTACHED
    assert said["attached"].json()["tools"] == ["crm.read_deal"], said["attached"].text
    assert said["after_attach"].authority.allowed_tools == {"crm.read_client", "crm.read_deal"}
    assert said["connector_off"].json()["tools"] == ["crm.read_client", "crm.read_deal"]
    assert said["after_off"].authority.allowed_tools == frozenset()
    assert said["connector_on"].json()["tools"] == ["crm.read_client", "crm.read_deal"]
    assert said["tool_off"].json()["tools"] == ["crm.read_deal"]
    assert said["final"].authority.allowed_tools == {"crm.read_client"}
    ledgered = entries(database, "compose_change")
    assert [
        (one.actor_id, one.subject, dict(one.details)["part"], dict(one.details)["direction"])
        for one in ledgered
    ] == [
        ("u_admin", f"agent:{AGENT}", "tool", "attached"),
        ("u_admin", f"agent:{AGENT}", "connector", "detached"),
        ("u_admin", f"agent:{AGENT}", "connector", "attached"),
        ("u_admin", f"agent:{AGENT}", "tool", "detached"),
    ]
