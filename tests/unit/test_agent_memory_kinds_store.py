"""An agent's memory kinds, set over HTTP against PostgreSQL: the row, the ledger, a stale page.

`tests/unit/test_agent_memory_kinds_routes.py` proves the route's decisions over memory; this
runs the routes over a database built to head, as the application role, and reads what reached the
table and the audit chain. Skips without a server that has pgvector.

Task ids: M39.7.1
"""

from __future__ import annotations

import httpx

from brain.agent_lifecycle_routes import INSTALL_PATH
from brain.agent_memory_kinds_routes import MEMORY_KINDS_PATH, REASON_CODE
from brain.agents.memory_kinds import ALL_KINDS
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_agent_lifecycle_routes import TEMPLATE_ID, VERSION
from tests.unit.test_agent_lifecycle_store import (
    a_published_version,
    post,
    pressed,
    through_0137,
)
from tests.unit.test_credential_writes import entries


def test_leaving_a_kind_out_reaches_the_row_and_the_ledger_and_a_stale_page_writes_neither() -> (
    None
):
    """An administrator installs an agent, then leaves the person's memory out over HTTP: the row
    holds four kinds, the audit chain holds one `compose_change` entry for the one kind detached,
    naming the person, the part and the reason, and a second press from a page that still shows all
    five is a 409 that writes nothing. Delete this and a kind can be left out with nothing recording
    who did it, or the column can stop being read by a run. **Skips without a server.**"""
    with through_0137("brain_agent_memory_kinds") as url:
        digest = a_published_version(url)

        async def switch(client: httpx.AsyncClient) -> tuple[str, int, int]:
            made = await post(
                client,
                INSTALL_PATH.format(template_id=TEMPLATE_ID, version=VERSION),
                {"expected_digest": digest},
            )
            agent_id = made.json()["agent"]["agent_id"]
            path = MEMORY_KINDS_PATH.format(agent_id=agent_id)
            four = [one for one in ALL_KINDS if one != "person"]
            first = await post(client, path, {"kinds": four, "expected": list(ALL_KINDS)})
            stale = await post(client, path, {"kinds": ["own"], "expected": list(ALL_KINDS)})
            return agent_id, first.status_code, stale.status_code

        before = len(entries(url))
        agent_id, first, stale = pressed(url, switch)
        [stored] = sql(url, "SELECT memory_kinds FROM agent.agent WHERE id = %s", agent_id)
        moved = [
            one
            for one in entries(url)[before:]
            if one.action.value == "compose_change" and one.details.get("part") == "memory"
        ]

    assert (first, stale) == (200, 409)
    assert sorted(stored[0]) == ["conversation", "own", "project", "task"]
    assert [(one.actor_id, one.subject) for one in moved] == [("u_admin", f"agent:{agent_id}")]
    assert [dict(one.details) for one in moved] == [
        {
            "part": "memory",
            "reference": "person",
            "direction": "detached",
            "reason_code": REASON_CODE,
        }
    ]
