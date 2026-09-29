"""An agent's memory over HTTP: who is answered as a missing agent, and what an agent with no memory
still shows.

Driven through the real application with signed-in people and a stub where the pool is. The
memories themselves, formed from a person's turn, corrected by the steward and deleted by the
person, are an install acceptance check in `brain.ops.acceptance_workspace`, which
`tests/unit/test_acceptance_workspace.py` runs against PostgreSQL and makes fail by breaking the
product.

Task ids: M39.4.1.1, M39.4.1.4, M39.4.2.1
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_memory_routes import (
    CHANGING_A_MEMORY_NEEDS_THE_STEWARD_OR_ITS_SUBJECT,
    AgentMemoryView,
    router,
)
from brain.agent_routes import one_agent, record_of
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reach_view import run_reach
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory.tiers import Tier
from brain.memory.turn import Turn
from brain.ops.memory_store import StoredFormations
from brain.session import make_session_factory
from brain.tables.agent import AgentRow
from brain.tables.learning import LearningRow
from tests.fixtures.console_http import Stub, console_client, gate_wiring, get, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

AGENT = "web_desk"

#: `u_admin` reads the Memory tab; `u_narrow` holds nothing. Both are in the audience.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": tuple(
        Grant(capability=capability, scope=Scope.unrestricted())
        for capability in (tab(Tab.MEMORY).read.requires, *(plane_capability(p) for p in Plane))
    ),
    "u_narrow": (),
}


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    entity = statement.column_descriptions[0].get("entity")
    if entity is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([agent_row(AGENT)] if wanted == AGENT else [])
    if entity is LearningRow:
        return Result([])
    return None


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        yield client, stub


def memory(client: TestClient, pid: str, agent_id: str) -> Any:
    return get(client, pid, f"{API_PREFIX}/agents/{agent_id}/memory")


def test_a_reader_without_the_memory_read_is_answered_as_an_agent_that_does_not_exist(
    served: tuple[TestClient, Stub],
) -> None:
    """The Memory address is never a way to learn whether an agent remembers anything: without
    the Memory tab's read the answer is the missing agent's. Delete this and anybody who can open
    an agent can read what it remembers."""
    client, _ = served
    refused = memory(client, "u_narrow", AGENT)
    missing = memory(client, "u_narrow", "no_such_agent")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]


def test_an_agent_with_no_memory_still_says_how_it_learns(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.4.2.1, and the sibling of the refusal: a reader of the Memory tab is answered for an
    agent that remembers nothing, with every list empty and the tiers it learns at, which never
    include tier three. Delete this and the Memory section's heading can stand over nothing,
    which is `brain.agent_routes.ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED`'s failure."""
    client, _ = served
    body = AgentMemoryView.model_validate(memory(client, "u_admin", AGENT).json())
    assert (body.curated, body.extracted, body.about_you, body.history) == ([], [], [], [])
    assert body.active_tiers == [int(one) for one in Tier if one is not Tier.GATED]


def test_a_memory_the_reader_is_not_shown_cannot_be_deleted_and_is_answered_as_missing(
    served: tuple[TestClient, Stub],
) -> None:
    """A delete names a memory by id, and an id is a loop somebody can run. A memory this reader's
    Memory section does not show is the missing agent's answer, and nothing is written. Delete
    this and the delete address says which memories exist."""
    client, stub = served
    response = client.post(
        f"{API_PREFIX}/agents/{AGENT}/memory/m{'a' * 25}/deletion", headers=headers("u_admin")
    )
    assert response.status_code == 404
    assert stub.commits == 0


# ------------------------------------------------------------------------- the database
#: The steward, `u_admin`, reads the Memory tab and the price list everywhere; the person,
#: `u_narrow`, reads both in web, where they sit. Both are in web in the directory the gate reads.
DB_GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_prefix": (
        *GRANTS["u_admin"],
        Grant(capability=Capability(value="read:price_list"), scope=Scope.unrestricted()),
    ),
    "u_admin": (
        *GRANTS["u_admin"],
        Grant(capability=Capability(value="read:price_list"), scope=Scope.unrestricted()),
    ),
    "u_narrow": tuple(
        Grant(capability=capability, scope=Scope.department("web"))
        for capability in (
            tab(Tab.MEMORY).read.requires,
            plane_capability(Plane.CONTENT),
            Capability(value="read:price_list"),
        )
    ),
}


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_memory_{uuid.uuid4().hex[:8]}") as url:
        yield url


def formed(url: str) -> list[str]:
    """The person's two memories, formed by the product's own step from one answered turn."""
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Web desk', 'Answer briefly.', 'main', 'department',"
        " 'u_admin', 'web', '{\"clauses\": []}', '{read:price_list}', '{}', '{}', 'none',"
        " 'u_admin')",
        AGENT,
    )

    async def go() -> list[str]:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            async with sessions() as session:
                row = (await session.execute(one_agent(AGENT))).scalar_one()
            record = record_of(row)
            assert record is not None
            reach = EntitlementSet(principal_id="u_narrow", grants=DB_GRANTS["u_narrow"])
            done = await StoredFormations(sessions).form(
                Turn(
                    trace_id="t" * 32,
                    principal_id="u_narrow",
                    said=(
                        "Remember that my invoices go to the finance inbox. I prefer short answers."
                    ),
                    answered=True,
                    reach=run_reach(reach, record),
                    at=datetime.now(UTC),
                    agent_id=AGENT,
                )
            )
            return list(done.memory_ids)
        finally:
            await built.dispose()

    return run(go)


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The memory routes over this database as the application role. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(DB_GRANTS)
            app.state.db_sessions = make_session_factory(built)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def test_the_steward_corrects_and_the_person_deletes_and_each_reaches_the_ledger(
    database: str,
) -> None:
    """M39.4.1.4 on PostgreSQL as the application role, end to end: the person's turn formed two
    memories; the steward sees both and corrects the stated one, which writes a replacement naming
    it; the person deletes the inferred one about themselves; each write is a `memory` entry on the
    ledger naming who. Delete this and the routes can answer 200 over writes the tables or their
    triggers refuse."""
    ids = formed(database)
    assert len(ids) == 2

    async def act(client: httpx.AsyncClient) -> tuple[Any, ...]:
        path = f"{API_PREFIX}/agents/{AGENT}/memory"
        seen = (await client.get(path, headers=headers("u_admin"))).json()
        stated = next(one for one in seen["curated"])
        inferred = next(one for one in seen["extracted"])
        edited = await client.post(
            f"{path}/{stated['memory_id']}/edit",
            json={"statement": "my invoices go to the accounts inbox"},
            headers=headers("u_admin"),
        )
        deleted = await client.post(
            f"{path}/{inferred['memory_id']}/deletion", headers=headers("u_narrow")
        )
        after = (await client.get(path, headers=headers("u_admin"))).json()
        return seen, edited, deleted, after

    seen, edited, deleted, after = pressed(database, act)
    assert edited.status_code == 200 and edited.json()["took_effect"] is True, edited.text
    assert deleted.status_code == 200 and deleted.json()["took_effect"] is True, deleted.text
    assert [one["statement"] for one in after["curated"]] == [
        "my invoices go to the accounts inbox"
    ]
    assert after["extracted"] == []
    ledgered = entries(database, "memory")
    assert {one.actor_id for one in ledgered} == {"u_admin", "u_narrow"}
    assert any(step["replaced_id"] for step in after["history"])
    assert seen["curated"][0]["changeable"] is True


def test_a_colleague_shown_a_memory_they_may_not_change_is_told_who_may(database: str) -> None:
    """The sibling refusal: a reader who holds the steward's grants and is neither the agent's
    steward nor the person a memory is about is shown the memory and refused its delete, in the
    sentence naming who may. Delete this and anybody who may read an agent's memory can change
    it."""
    formed(database)

    async def act(client: httpx.AsyncClient) -> Any:
        path = f"{API_PREFIX}/agents/{AGENT}/memory"
        seen = (await client.get(path, headers=headers("u_prefix"))).json()
        target = seen["curated"][0]["memory_id"]
        return seen, await client.post(f"{path}/{target}/deletion", headers=headers("u_prefix"))

    seen, refused = pressed(database, act)
    assert seen["curated"][0]["changeable"] is False
    assert refused.status_code == 403
    assert refused.json()["message"] == CHANGING_A_MEMORY_NEEDS_THE_STEWARD_OR_ITS_SUBJECT
