"""An agent's monthly budget over HTTP: who may set it, who is told the agent does not exist, and
that a second setting supersedes the first on the ledger.

The refusals are driven through the real application with signed-in people and a stub where the
pool is: a caller who may not see the agent gets the 404 a missing agent gets, and a caller who may
see it without the budget authority over its department gets the sentence naming the role. The
database half sets a budget twice through the route as the application role and reads back two
versions and two ledger entries naming the administrator.

Task ids: M39.1.3.4
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_workspace_routes import (
    BUDGET_AUTHORITY,
    SETTING_A_BUDGET_NEEDS_THE_BUDGET_ROLE,
    router,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.session import make_session_factory
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import Stub, console_client, gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

AGENT = "web_desk"
HIDDEN_AGENT = "finance_desk"

#: `u_admin` sits in web and holds the budget authority over web; `u_prefix` sits in web too and
#: holds it over finance only; `u_narrow` sits in web and holds nothing. The web desk is visible to
#: all three, and the finance desk to none of them.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=BUDGET_AUTHORITY, scope=Scope.department("web")),),
    "u_prefix": (Grant(capability=BUDGET_AUTHORITY, scope=Scope.department("finance")),),
    "u_narrow": (),
}

ROWS = {
    AGENT: agent_row(AGENT, level=Visibility.DEPARTMENT, department="web"),
    HIDDEN_AGENT: agent_row(HIDDEN_AGENT, level=Visibility.DEPARTMENT, department="finance"),
}


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    described = statement.column_descriptions
    if described[0].get("entity") is AgentRow and len(described) == 1:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    return None


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        yield client, stub


def put(client: TestClient, pid: str, agent_id: str, body: Mapping[str, Any]) -> Any:
    return client.put(
        f"{API_PREFIX}/agents/{agent_id}/budget", json=dict(body), headers=headers(pid)
    )


BODY = {"ceiling_minor": 25000, "reason": "The web team's month."}


def test_a_caller_without_the_budget_role_over_the_agents_department_is_told_which_role(
    served: tuple[TestClient, Stub],
) -> None:
    """Somebody who may see the agent and holds the budget authority over another department, or
    none, is refused with the sentence naming the role, and nothing is written. Delete this and
    anybody who can open a company agent can set what it may spend."""
    client, stub = served
    for pid in ("u_prefix", "u_narrow"):
        refused = put(client, pid, AGENT, BODY)
        assert refused.status_code == 403
        assert refused.json()["message"] == SETTING_A_BUDGET_NEEDS_THE_BUDGET_ROLE
    assert stub.commits == 0


def test_an_agent_the_caller_may_not_see_is_the_404_an_agent_that_does_not_exist_gets(
    served: tuple[TestClient, Stub],
) -> None:
    """The budget address is a loop over slugs like every other agent address. Delete this and a
    refusal naming the budget role for a hidden agent tells the caller the agent exists."""
    client, _ = served
    hidden = put(client, "u_narrow", HIDDEN_AGENT, BODY)
    missing = put(client, "u_narrow", "no_such_agent", BODY)
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["message"] == missing.json()["message"]


def test_a_ceiling_of_nothing_or_no_reason_is_refused_before_anything_is_read(
    served: tuple[TestClient, Stub],
) -> None:
    """A ceiling below one minor unit binds every run at once, and a budget with no reason is a
    change nobody can be asked about. Delete this and either reaches the ledger."""
    client, stub = served
    for body in ({"ceiling_minor": 0, "reason": "x"}, {"ceiling_minor": 100, "reason": ""}):
        assert put(client, "u_admin", AGENT, body).status_code == 422
    assert stub.statements == []


# ------------------------------------------------------------------------- the database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_budget_{uuid.uuid4().hex[:8]}") as url:
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The budget route over this database as the application role. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def test_setting_a_budget_twice_writes_two_versions_and_two_ledger_entries(
    database: str,
) -> None:
    """M39.1.3.4's budget on PostgreSQL as the application role: the department's budget
    administrator sets the agent's monthly ceiling, sets it again, and the table holds version one
    and version two, each ledgered under the agent and naming them, with the request's own trace.
    Delete this and the route can answer 200 over a write the table or its trigger refuses."""
    sql(
        database,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Web desk', 'Answer briefly.', 'main', 'department', 'u_admin',"
        " 'web', '{\"clauses\": []}', '{}', '{}', '{}', 'none', 'u_admin')",
        AGENT,
    )

    async def twice(client: httpx.AsyncClient) -> list[httpx.Response]:
        path = f"{API_PREFIX}/agents/{AGENT}/budget"
        first = await client.put(path, json=BODY, headers=headers("u_admin"))
        second = await client.put(
            path, json={**BODY, "ceiling_minor": 50000}, headers=headers("u_admin")
        )
        return [first, second]

    first, second = pressed(database, twice)
    assert (first.status_code, second.status_code) == (200, 200), first.text
    assert (first.json()["version"], second.json()["version"]) == (1, 2)
    stored = sql(
        database,
        "SELECT version, ceiling_minor, author FROM ops.budget_version"
        " WHERE level = 'agent' AND subject = %s AND period = 'month' ORDER BY version",
        AGENT,
    )
    assert [tuple(one) for one in stored] == [(1, 25000, "u_admin"), (2, 50000, "u_admin")]
    ledgered = [one for one in entries(database, "setting") if one.subject == f"agent:{AGENT}"]
    assert [(one.actor_id, one.details["budget_period"]) for one in ledgered] == [
        ("u_admin", "month"),
        ("u_admin", "month"),
    ]
    assert all(not one.trace_id.startswith("tx.") for one in ledgered)
