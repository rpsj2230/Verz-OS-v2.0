"""An agent's capability detail and a person's preview over HTTP: who is answered as a missing
agent, and what the audience block tells a reader.

Driven through the real application with signed-in people and a stub where the pool is. The
positive cases over a real database, with a library, documents and a registry, are the install
acceptance checks in `brain.ops.acceptance_workspace`, which
`tests/unit/test_acceptance_workspace.py` runs against PostgreSQL and makes fail by breaking the
product.

Task ids: M39.3.1.1, M39.3.1.3, M39.3.1.4
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_capability_routes import AgentCapabilitiesView, router
from brain.agents.model import AUDIENCE_IS_NOT_AUTHORITY
from brain.agents.template import SkillRef
from brain.api import API_PREFIX
from brain.console.reach_view import PREVIEW_DISCLOSURE
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_agent_routes import agent_row, install_rows
from tests.unit.test_connector_routes import Records

AGENT = "web_desk"
HIDDEN_AGENT = "finance_desk"
COMPANY_AGENT = "company_desk"
PINNED = SkillRef(name="triage", digest="a" * 64)

#: `u_admin` sits in web and may read grants, which is who may preview; `u_narrow` sits in web
#: and holds nothing; `u_elsewhere` sits in finance; `u_wide` reads the Settings tab and the
#: Skills screen, which is who is sent an agent's skills.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=PREVIEW_DISCLOSURE, scope=Scope.unrestricted()),),
    "u_narrow": (),
    "u_elsewhere": (),
    "u_wide": tuple(
        Grant(capability=capability, scope=Scope.unrestricted())
        for capability in (
            tab(Tab.SETTINGS).read.requires,
            screen("skills").read.requires,
            *(plane_capability(plane) for plane in Plane),
        )
    ),
}

ROWS = {
    AGENT: agent_row(AGENT, level=Visibility.DEPARTMENT, department="web"),
    HIDDEN_AGENT: agent_row(HIDDEN_AGENT, level=Visibility.DEPARTMENT, department="finance"),
    COMPANY_AGENT: agent_row(COMPANY_AGENT),
}

#: The company agent's install, pinned to one skill by digest.
INSTALL = install_rows(COMPANY_AGENT, skills=(PINNED,))


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    described = statement.column_descriptions
    columns = [one["name"] for one in described]
    if described[0].get("entity") is AgentRow and len(described) == 1:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    if len(described) == 2:
        # The agent's install, which only the company agent has.
        where = statement.whereclause
        wanted = "" if where is None else str(getattr(getattr(where, "right", None), "value", ""))
        return Result([Row(INSTALL[:2])] if wanted == COMPANY_AGENT else [])
    if columns == ["principal_id", "skill_name", "used_at"]:
        return Result([])
    return None


class NoAttempts:
    """`ConnectorSyncRecords` holding no attempt at all."""

    async def states(self) -> Mapping[str, Any]:
        return {}


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        state = client.app.state  # type: ignore[attr-defined]
        state.connector_records = Records(())
        state.connector_sync_records = NoAttempts()
        yield client, stub


def capabilities(client: TestClient, pid: str, agent_id: str) -> Any:
    return get(client, pid, f"{API_PREFIX}/agents/{agent_id}/capabilities")


def preview(client: TestClient, pid: str, agent_id: str, person: str) -> Any:
    return client.post(
        f"{API_PREFIX}/agents/{agent_id}/preview",
        json={"person_id": person},
        headers=headers(pid),
    )


def test_an_agent_the_caller_may_not_see_is_the_404_an_agent_that_does_not_exist_gets(
    served: tuple[TestClient, Stub],
) -> None:
    """The capability address is a loop over slugs like every agent address. Delete this and the
    detail tells a caller which agents exist outside their audience."""
    client, _ = served
    hidden = capabilities(client, "u_narrow", HIDDEN_AGENT)
    missing = capabilities(client, "u_narrow", "no_such_agent")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["message"] == missing.json()["message"]
    assert capabilities(client, "u_elsewhere", HIDDEN_AGENT).status_code == 200


def test_the_audience_block_says_who_finds_the_agent_and_that_finding_it_gives_no_access(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.3.1.1 and M39.3.1.3: the level, the department and whether the reader is in the
    audience, under the sentence that availability is discovery and never authority. Delete this
    and the block can say who may find an agent as though it said what they may reach."""
    client, _ = served
    body = AgentCapabilitiesView.model_validate(capabilities(client, "u_narrow", AGENT).json())
    assert (body.availability.level, body.availability.department) == ("department", "web")
    assert body.availability.reader_is_included is True
    assert body.availability.words == AUDIENCE_IS_NOT_AUTHORITY
    # A reader sent nothing about skills or knowledge is sent no block for either, not an empty one.
    assert (body.skills, body.offers, body.knowledge) == ([], [], None)


def test_a_previewer_who_may_not_read_grants_is_answered_as_a_missing_agent(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.3.1.4's disclosure: previewing a person's run is reading what they hold, so a reader
    without the People screen's read gets the answer a missing agent gets and nobody's grants are
    read for them. Delete this and anybody who can open an agent can read a colleague's reach."""
    client, stub = served
    refused = preview(client, "u_narrow", AGENT, "u_admin")
    missing = preview(client, "u_narrow", "no_such_agent", "u_admin")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]
    assert not [one for one in stub.statements if "capability_grant" in str(one)]


def test_an_agents_skills_reach_only_a_reader_of_its_settings_and_the_skills_screen(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.2.2.1's chips travel where the workspace's do: with the Settings tab and the Skills
    screen's read. A reader holding neither is sent no chip and no offer, and a reader holding
    both is sent the pinned skill by name and digest. Delete this and a skill's name, which
    describes a procedure somebody wants run, reaches everybody who can open the agent."""
    client, _ = served
    narrow = AgentCapabilitiesView.model_validate(
        capabilities(client, "u_narrow", COMPANY_AGENT).json()
    )
    wide = AgentCapabilitiesView.model_validate(
        capabilities(client, "u_wide", COMPANY_AGENT).json()
    )
    assert (narrow.skills, narrow.unused_skills, narrow.offers) == ([], [], [])
    assert [(one.name, one.digest, one.runs) for one in wide.skills] == [
        (PINNED.name, PINNED.digest, 0)
    ]
    assert wide.unused_skills == [PINNED.name]
