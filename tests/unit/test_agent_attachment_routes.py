"""Attaching and detaching an agent's tools and connectors over HTTP, on PostgreSQL.

Driven through the real application with signed-in people, the application role and a real tool
registry, so the ceiling check, `0196`'s policies and both its ledger triggers are the ones an
install has, and the answer route's own roster reader is asked what a run would now be handed: the
tools it carries, and through `entitlement_ceiling` the sources its connector list opens.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

import httpx
import pytest

from brain.agent_attachment_routes import (
    CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE,
    CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE,
    FROM_THE_AGENT_PAGE,
    router,
)
from brain.agent_roster import agent_roster_for
from brain.agents.attachments import ALREADY_ATTACHED, CANNOT_BE_ATTACHED, NOTHING_TO_ATTACH
from brain.agents.binding import providers
from brain.agents.model import entitlement_ceiling
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Scope
from brain.ops.attachment_store import AgentMovedError, StoredAttachments
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

#: A shipped connector and the read on one entity it provides, through the binding's own map.
CONNECTOR = "freshdesk"
SOURCED = f"read:{min(e for e, n in providers().items() if n == CONNECTOR)}"

#: `u_narrow` is the agent's steward and reaches the connector's read; `u_admin` holds the tool and
#: connector roles and does not reach it; `u_prefix` reaches everything and holds no role; `u_wide`
#: holds everything and sits in another department, so the agent is not one they can see.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": everywhere(*SETTINGS_READ, "admin:tool", "admin:connector", *REACHES),
    "u_prefix": everywhere(*SETTINGS_READ, *REACHES, SOURCED),
    "u_narrow": everywhere(*SETTINGS_READ, *REACHES, SOURCED),
    "u_wide": everywhere(*SETTINGS_READ, "admin:tool", "admin:connector", *REACHES, SOURCED),
}


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_attachments_{uuid.uuid4().hex[:8]}") as url:
        sql(
            url,
            "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
            " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
            " created_by) VALUES (%s, 'Sales desk', 'Answer briefly.', 'main', 'department',"
            " 'u_narrow', 'web', '{\"clauses\": []}', %s, '{crm.read_client}', '{}', 'none',"
            " 'u_admin')",
            AGENT,
            ["read:client", "read:deal", "write:deal.stage", SOURCED],
        )
        yield url


def pressed[T](
    url: str, presses: Callable[[httpx.AsyncClient, Any, StoredAttachments], Awaitable[T]]
) -> T:
    """The attachment routes over this database as the application role, with a real registry,
    the answer route's roster reader and the store over the same sessions. No lifespan runs."""

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
                return await presses(
                    client, agent_roster_for(sessions), StoredAttachments(sessions)
                )
        finally:
            await built.dispose()

    return run(go)


def press(part: str, reference: str, attached: bool) -> dict[str, Any]:
    return {"part": part, "reference": reference, "attached": attached}


def test_tools_and_connectors_are_attached_within_the_ceiling_and_a_run_carries_only_those(
    database: str,
) -> None:
    """**M39.8.6, M39.2.1.2 and M39.1.1.3 on PostgreSQL.** Tools: the reader is offered only what
    the ceiling and their reach admit; without the tool role a press is refused naming it; a tool
    above the ceiling is refused in one sentence; a tool is attached and detached, and the answer
    route's roster hands a run exactly the tools the agent carries after each.

    Connectors, on the agent's own list: the steward attaches one, the column holds it and a run's
    ceiling reads through it; a holder of neither the stewardship nor the connector role is refused
    naming them; the connector administrator who does not reach what it opens is refused in one
    sentence; a reader the agent is not visible to gets the missing agent's 404; a second attach is
    told it is attached; the administrator detaches it, asking nothing of their reach, and the
    ceiling no longer reads the source. Every press is one `compose_change` entry naming who, what,
    which way and why, the connectors' written by the agent row's own trigger.

    Delete this and a press can answer 200 over a row the table refuses, a source is bound by
    somebody who could not read it, or a detach changes the page and not what a run is handed."""

    async def act(client: httpx.AsyncClient, roster: Any, store: StoredAttachments) -> Any:
        def mine(found: Any) -> Any:
            return {one.agent_id: one for one in found}[AGENT]

        said: dict[str, Any] = {}
        said["offered"] = (await client.get(PATH, headers=headers("u_admin"))).json()
        said["offered_steward"] = (await client.get(PATH, headers=headers("u_narrow"))).json()
        said["refused"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", True), headers=headers("u_prefix")
        )
        said["above"] = await client.post(
            PATH, json=press("tool", "crm.update_deal", True), headers=headers("u_admin")
        )
        said["attached"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", True), headers=headers("u_admin")
        )
        said["after_attach"] = mine(await roster())
        on = press("connector", CONNECTOR, True)
        said["no_role"] = await client.post(PATH, json=on, headers=headers("u_prefix"))
        said["no_reach"] = await client.post(PATH, json=on, headers=headers("u_admin"))
        said["unseen"] = await client.post(PATH, json=on, headers=headers("u_wide"))
        said["missing"] = await client.post(
            f"{API_PREFIX}/agents/no_such_agent/attachments", json=on, headers=headers("u_wide")
        )
        said["bound"] = await client.post(PATH, json=on, headers=headers("u_narrow"))
        said["after_bound"] = mine(await roster())
        said["again"] = await client.post(PATH, json=on, headers=headers("u_narrow"))
        said["unbound"] = await client.post(
            PATH, json=press("connector", CONNECTOR, False), headers=headers("u_admin")
        )
        said["after_unbound"] = mine(await roster())
        said["tool_off"] = await client.post(
            PATH, json=press("tool", "crm.read_deal", False), headers=headers("u_admin")
        )
        said["final"] = mine(await roster())
        try:
            await store.bind_connectors(
                agent_id=AGENT,
                was=(CONNECTOR,),
                becomes=(),
                by="u_admin",
                reason_code=FROM_THE_AGENT_PAGE,
                ent_hash="0" * 32,
                trace_id="t-stale",
            )
        except AgentMovedError:
            said["stale"] = "refused"
        return said

    said = pressed(database, act)
    assert [one["name"] for one in said["offered"]["tools"]] == ["crm.read_deal"]
    assert said["offered"]["connectors"] == []
    assert said["offered_steward"]["connectors"] == [CONNECTOR]
    assert said["refused"].status_code == 403
    assert said["refused"].json()["message"] == CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE
    assert said["above"].status_code == 409
    assert said["above"].json()["message"] == CANNOT_BE_ATTACHED
    assert said["attached"].json()["tools"] == ["crm.read_deal"], said["attached"].text
    assert said["after_attach"].authority.allowed_tools == {"crm.read_client", "crm.read_deal"}

    assert said["no_role"].status_code == 403
    assert said["no_role"].json()["message"] == CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE
    assert said["no_reach"].status_code == 409
    assert said["no_reach"].json()["message"] == NOTHING_TO_ATTACH
    assert said["unseen"].status_code == said["missing"].status_code == 404
    assert said["unseen"].json()["message"] == said["missing"].json()["message"]
    assert said["bound"].status_code == 200, said["bound"].text
    assert said["bound"].json()["connectors"] == [CONNECTOR]
    assert said["after_bound"].authority.connectors == (CONNECTOR,)
    sourced = Capability(value=SOURCED)
    assert entitlement_ceiling(said["after_bound"]).holds(sourced)
    assert said["again"].status_code == 409
    assert said["again"].json()["message"] == ALREADY_ATTACHED
    assert said["unbound"].json()["connectors"] == [], said["unbound"].text
    assert not entitlement_ceiling(said["after_unbound"]).holds(sourced)
    assert said["tool_off"].json()["tools"] == ["crm.read_deal"]
    assert said["final"].authority.allowed_tools == {"crm.read_client"}
    assert said["stale"] == "refused"
    assert sql(database, "SELECT connectors FROM agent.agent WHERE id = %s", AGENT) == [([],)]

    ledgered = entries(database, "compose_change")
    assert [
        (
            one.actor_id,
            one.subject,
            dict(one.details)["part"],
            dict(one.details)["reference"],
            dict(one.details)["direction"],
            dict(one.details)["reason_code"],
        )
        for one in ledgered
    ] == [
        ("u_admin", f"agent:{AGENT}", "tool", "crm.read_deal", "attached", FROM_THE_AGENT_PAGE),
        ("u_narrow", f"agent:{AGENT}", "connector", CONNECTOR, "attached", FROM_THE_AGENT_PAGE),
        ("u_admin", f"agent:{AGENT}", "connector", CONNECTOR, "detached", FROM_THE_AGENT_PAGE),
        ("u_admin", f"agent:{AGENT}", "tool", "crm.read_deal", "detached", FROM_THE_AGENT_PAGE),
    ]


def test_a_connector_written_by_a_statement_is_on_the_ledger_and_says_nobody_explained_it(
    database: str,
) -> None:
    """The agent row's trigger records a connector list moved by anything, not only the console:
    a statement typed at a prompt that adds one and takes another away is two `compose_change`
    entries, attributed to the database role, marked inferred, with the reason that says nobody
    gave one. An update that leaves the list alone records nothing about connectors. Delete this
    and a source bound behind the console reaches every run with no record of who bound it."""
    sql(database, "UPDATE agent.agent SET connectors = '{hubspot}' WHERE id = %s", AGENT)
    sql(database, "UPDATE agent.agent SET connectors = %s WHERE id = %s", [CONNECTOR], AGENT)
    sql(database, "UPDATE agent.agent SET persona = 'Answer at length.' WHERE id = %s", AGENT)

    ledgered = entries(database, "compose_change")
    assert [
        (
            dict(one.details)["reference"],
            dict(one.details)["direction"],
            dict(one.details)["reason_code"],
            dict(one.details).get("actor"),
        )
        for one in ledgered
    ] == [
        ("hubspot", "attached", "agent_row_changed", "inferred"),
        (CONNECTOR, "attached", "agent_row_changed", "inferred"),
        ("hubspot", "detached", "agent_row_changed", "inferred"),
    ]


def test_an_archived_agents_connectors_are_not_written(database: str) -> None:
    """Archive is terminal, so the store's write refuses an archived agent as it refuses a list
    that moved since it was read, and the column is left as it was. The positive half is the
    steward's bind in the test above, through the same write. Delete this and an archived agent,
    which no route can bring back, can still be bound to a source by a press made a moment
    before it was archived."""
    sql(database, "UPDATE agent.agent SET archived_at = now() WHERE id = %s", AGENT)

    async def act(client: httpx.AsyncClient, roster: Any, store: StoredAttachments) -> str:
        try:
            await store.bind_connectors(
                agent_id=AGENT,
                was=(),
                becomes=(CONNECTOR,),
                by="u_narrow",
                reason_code=FROM_THE_AGENT_PAGE,
                ent_hash="0" * 32,
                trace_id="t-archived",
            )
        except AgentMovedError:
            return "refused"
        return "written"

    assert pressed(database, act) == "refused"
    assert sql(database, "SELECT connectors FROM agent.agent WHERE id = %s", AGENT) == [([],)]
