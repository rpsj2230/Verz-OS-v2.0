"""Where a link to one tab of one agent lands, over HTTP, and the one 404 for every failure.

Driven through the real application with signed-in people over a stub pool that answers the one
agent row, so the audience question, the tab strip and the 404 are the product's own. The alert
that carries such a link is `brain.automation_paused_told`, tested there.

Task ids: M39.1.2.4
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_link_routes import LANDING_PATH, agent_named_by, router
from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, deep_link, tab
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import Stub, console_client
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row

AGENT = "web_desk"
PATH = f"{API_PREFIX}{LANDING_PATH}"


def everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


PLANES = tuple(plane_capability(one) for one in Plane)

#: `u_admin` reads every tab; `u_narrow` reads the Memory tab alone; `u_prefix` reads nothing.
#: The agent is the web department's, which `u_wide` (sales) is outside.
GRANTS = {
    "u_admin": everywhere(*(tab(one).read.requires for one in Tab), *PLANES),
    "u_narrow": everywhere(tab(Tab.MEMORY).read.requires, *PLANES),
    "u_prefix": (),
    "u_wide": everywhere(*(tab(one).read.requires for one in Tab), *PLANES),
}


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    if statement.column_descriptions[0].get("entity") is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        found = agent_row(AGENT, level=Visibility.DEPARTMENT, department="web")
        return Result([found] if wanted == AGENT else [])
    return None


@pytest.fixture
def served() -> Iterator[TestClient]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        assert isinstance(stub, Stub)
        stub.answerers.append(answer)
        yield client


def landing(client: TestClient, pid: str, link: str) -> Any:
    return client.get(PATH, params={"link": link}, headers=get_headers(pid))


def get_headers(pid: str) -> dict[str, str]:
    from tests.fixtures.console_http import headers

    return headers(pid)


def test_a_link_to_a_tab_the_reader_holds_lands_there_with_its_own_address(
    served: TestClient,
) -> None:
    """**The positive case.** A reader holding the Settings tab follows a link to it and is told
    the agent, the tab and the address `deep_link` makes; a reader holding Memory alone lands on
    Memory. Delete this and every link could be refused, which the refusals below would not
    notice."""
    settings = landing(served, "u_admin", deep_link(AGENT, Tab.SETTINGS))
    memory = landing(served, "u_narrow", deep_link(AGENT, Tab.MEMORY))

    assert settings.status_code == 200, settings.text
    assert settings.json() == {
        "agent_id": AGENT,
        "tab": "settings",
        "address": f"/agents/{AGENT}/settings",
    }
    assert memory.json()["tab"] == "memory"


def test_every_way_a_link_can_fail_is_the_one_404_an_agent_that_does_not_exist_gets(
    served: TestClient,
) -> None:
    """`workspace.A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`, served: a tab the reader holds
    no grant for, an agent outside their audience, an agent that does not exist, a tab that does
    not exist, a link missing its tab, a link with a third segment and a link that is not an agent
    link at all are one answer. Delete this and the address bar answers which agents exist and
    which tabs a person may not open."""
    asked = [
        landing(served, "u_narrow", deep_link(AGENT, Tab.SETTINGS)),
        landing(served, "u_wide", deep_link(AGENT, Tab.SETTINGS)),
        landing(served, "u_admin", deep_link("no_such_agent", Tab.SETTINGS)),
        landing(served, "u_admin", f"/agents/{AGENT}/nowhere"),
        landing(served, "u_admin", f"/agents/{AGENT}"),
        landing(served, "u_admin", f"/agents/{AGENT}/settings/more"),
        landing(served, "u_admin", "/somewhere/else"),
        landing(served, "u_prefix", deep_link(AGENT, Tab.MEMORY)),
    ]

    assert {one.status_code for one in asked} == {404}
    assert len({one.json()["message"] for one in asked}) == 1


def test_the_agent_a_link_names_is_read_off_its_first_segment_and_decides_nothing() -> None:
    """`agent_named_by` only says which row to read. Delete this and a malformed link could read
    a row named by its tail, or a link with no agent read every row."""
    assert agent_named_by(f"/agents/{AGENT}/memory") == AGENT
    assert agent_named_by(f"/agents/{AGENT}") == AGENT
    assert agent_named_by("/agents/") is None
    assert agent_named_by("/elsewhere/web_desk/memory") is None


def test_the_address_is_the_route_the_console_draws_the_tab_on() -> None:
    """The console opens `/agents/:agentId/:tab` for Settings, Automations and Memory, so a link
    `deep_link` makes for those is one the console can open. Delete this and the alert's link
    points at an address the console does not route."""
    for one in (Tab.SETTINGS, Tab.AUTOMATIONS, Tab.MEMORY):
        assert deep_link(AGENT, one) == f"/agents/{AGENT}/{one.value}"
