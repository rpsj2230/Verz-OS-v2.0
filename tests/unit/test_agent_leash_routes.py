"""An agent's leash over HTTP: moved, judged, tripped, pinned and reviewed, on PostgreSQL.

Driven through the real application with signed-in people and the application role against a
database at head, so `0158`'s policies, its checks and its ledger trigger are the ones an install
has. The run of an agent that produces supervised actions does not exist yet (the gate's
`govern` is called by the builder's rehearsal alone), so the actions are recorded through the
store's own `record_action`, which is what that run would call. The whole path on an install is an
acceptance check in `brain.ops.acceptance_workspace`.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_leash_routes import (
    LEASH_AUTHORITY,
    MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE,
    NOT_DUE_YET,
    router,
)
from brain.agents.leash_moves import BREAKER_METRIC, THE_PROPOSER_CANNOT_CONFIRM
from brain.agents.supervision import SHADOW_REVIEW_PERIOD, ShadowPin
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ActionRecord, Route
from brain.ops.leash_store import StoredLeash
from brain.session import make_session_factory
from brain.tables.agent import AgentRow
from brain.tables.leash import PinOutcome
from tests.fixtures.console_http import Stub, console_client, gate_wiring, get, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

AGENT = "web_desk"
TARGET = "quote.send"
PATH = f"{API_PREFIX}/agents/{AGENT}"


def everywhere(*capabilities: Capability | str) -> tuple[Grant, ...]:
    return tuple(
        Grant(
            capability=one if isinstance(one, Capability) else Capability(value=one),
            scope=Scope.unrestricted(),
        )
        for one in capabilities
    )


SETTINGS_READ: tuple[Capability, ...] = (
    tab(Tab.SETTINGS).read.requires,
    *(plane_capability(one) for one in Plane),
)

#: `u_admin` and `u_prefix` hold the leash role and read the People screen; `u_narrow` reads the
#: Settings tab and holds no leash role.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": everywhere(*SETTINGS_READ, LEASH_AUTHORITY, screen("people").read.requires),
    "u_prefix": everywhere(*SETTINGS_READ, LEASH_AUTHORITY),
    "u_narrow": everywhere(*SETTINGS_READ),
    "u_elsewhere": (),
}


# ------------------------------------------------------------------------- the refusal
def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    if statement.column_descriptions[0].get("entity") is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([agent_row(AGENT)] if wanted == AGENT else [])
    return None


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        yield client, stub


def test_a_reader_without_the_settings_read_is_answered_as_an_agent_that_does_not_exist(
    served: tuple[TestClient, Stub],
) -> None:
    """The leash is configuration, behind the Settings tab as the Profile is. Delete this and the
    leash address tells anybody who can open an agent how much it may do unwatched."""
    client, _ = served
    refused = get(client, "u_elsewhere", f"{PATH}/leash")
    missing = get(client, "u_elsewhere", f"{API_PREFIX}/agents/no_such_agent/leash")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]


# ------------------------------------------------------------------------- the database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_leash_{uuid.uuid4().hex[:8]}") as url:
        sql(
            url,
            "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
            " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
            " created_by) VALUES (%s, 'Web desk', 'Answer briefly.', 'main', 'company',"
            " 'u_narrow', NULL, '{\"clauses\": []}', '{}', '{}', '{}', 'none', 'u_admin')",
            AGENT,
        )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient, StoredLeash], Awaitable[T]]) -> T:
    """The leash routes over this database as the application role. No lifespan runs, so no
    tool registry: every target is judged as touching money, which is the fail-closed default."""

    async def go() -> T:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = sessions
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client, StoredLeash(sessions))
        finally:
            await built.dispose()

    return run(go)


def action(n: int, *, at: datetime, route: Route = Route.SIMULATE) -> ActionRecord:
    return ActionRecord(
        trace_id=f"t{n}",
        agent_id=AGENT,
        tool_name=TARGET,
        target=TARGET,
        principal_id="u_narrow",
        ent_hash="0" * 32,
        action_digest=hashlib.sha256(f"{AGENT}-{n}".encode()).hexdigest(),
        route=route,
        tier=AutonomyTier.SHADOW,
        at=at,
    )


def move(to: str) -> dict[str, Any]:
    return {"target": TARGET, "to": to}


def test_a_rung_rises_on_counted_evidence_by_two_people_falls_at_once_and_trips_on_a_verdict(
    database: str,
) -> None:
    """**M39.3.2.1 to M39.3.2.5 on PostgreSQL.** Without the role a press is refused in the
    sentence naming it. Ten simulated actions judged unchanged are the evidence; across the money
    boundary the first press is a proposal, the proposer's second press is refused, another
    holder's is the raise, and the leash reads Assisted. A lowering is immediate. Raised again, one
    action rejected trips the breaker to Shadow naming its metric. The history holds every move
    oldest first with its approvers and evidence, and each move that moved a rung, and no
    proposal, is one ledger entry naming who.

    Delete this and the routes can answer 200 over rows the table's checks refuse, or a rung can
    move on a single person's press across a boundary that asks for two."""
    earlier = datetime.now(UTC) - timedelta(hours=1)

    async def act(client: httpx.AsyncClient, store: StoredLeash) -> Any:
        said: dict[str, Any] = {}
        said["refused"] = await client.post(
            f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_narrow")
        )
        for n in range(10):
            await store.record_action(action(n, at=earlier + timedelta(seconds=n)))
        for n in range(10):
            digest = action(n, at=earlier).action_digest
            await client.post(
                f"{PATH}/supervision/verdicts",
                json={"action_digest": digest, "verdict": "approved"},
                headers=headers("u_admin"),
            )
        said["proposed"] = await client.post(
            f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_admin")
        )
        said["own"] = await client.post(
            f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_admin")
        )
        said["raised"] = await client.post(
            f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_prefix")
        )
        said["after_raise"] = (await client.get(f"{PATH}/leash", headers=headers("u_admin"))).json()
        said["lowered"] = await client.post(
            f"{PATH}/leash/moves", json=move("shadow"), headers=headers("u_admin")
        )
        # A new record since the lowering, two people again, then one action rejected.
        for n in range(10, 20):
            await store.record_action(action(n, at=datetime.now(UTC)))
            await client.post(
                f"{PATH}/supervision/verdicts",
                json={
                    "action_digest": action(n, at=earlier).action_digest,
                    "verdict": "approved",
                },
                headers=headers("u_admin"),
            )
        await client.post(f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_admin"))
        await client.post(f"{PATH}/leash/moves", json=move("assisted"), headers=headers("u_prefix"))
        wrong = action(20, at=datetime.now(UTC), route=Route.SUSPEND)
        await store.record_action(wrong)
        said["tripped"] = await client.post(
            f"{PATH}/supervision/verdicts",
            json={"action_digest": wrong.action_digest, "verdict": "rejected"},
            headers=headers("u_admin"),
        )
        said["final"] = (await client.get(f"{PATH}/leash", headers=headers("u_admin"))).json()
        said["unnamed"] = (await client.get(f"{PATH}/leash", headers=headers("u_prefix"))).json()
        return said

    said = pressed(database, act)
    assert said["refused"].status_code == 403
    assert said["refused"].json()["message"] == MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE
    assert said["proposed"].json()["kind"] == "proposed", said["proposed"].text
    assert said["own"].status_code == 409
    assert said["own"].json()["message"] == THE_PROPOSER_CANNOT_CONFIRM
    assert said["raised"].json() == {
        "target": TARGET,
        "kind": "raised",
        "was": "shadow",
        "became": "assisted",
    }
    assert [(one["target"], one["rung"]) for one in said["after_raise"]["entries"]] == [
        (TARGET, "assisted")
    ]
    assert said["lowered"].json()["kind"] == "lowered"
    assert said["tripped"].json()["tripped"] == [TARGET]
    final = said["final"]
    assert [(one["target"], one["rung"]) for one in final["entries"]] == [(TARGET, "shadow")]
    kinds = [one["kind"] for one in final["history"]]
    assert kinds == ["proposed", "raised", "lowered", "proposed", "raised", "tripped"]
    raised = final["history"][1]
    assert (raised["approver"], raised["second_approver"]) == ("u_admin", "u_prefix")
    assert (raised["clean_runs"], raised["agreement_rate"]) == (10, 1.0)
    trip = final["history"][-1]
    assert (trip["metric"], trip["measured"], trip["threshold"]) == (BREAKER_METRIC, 0.0, 0.9)
    assert said["unnamed"]["history"][1]["approver"] == ""
    ledgered = entries(database, "leash_change")
    assert [(one.actor_id, dict(one.details)["kind"]) for one in ledgered] == [
        ("u_prefix", "raised"),
        ("u_admin", "lowered"),
        ("u_prefix", "raised"),
        ("u_admin", "tripped"),
    ]


def test_a_pin_holds_the_agent_down_is_not_reviewed_early_and_extends_when_nobody_judged(
    database: str,
) -> None:
    """**M39.8.2 on PostgreSQL.** Pinning writes a row with its review thirty days out and holds
    every rung at Shadow; a review before it is due is refused; a pin whose review has come due
    with nothing judged is extended from now, keeping its start. Delete this and a pin ends when
    a date passes, or a review asked early decides on an empty window."""

    async def act(client: httpx.AsyncClient, store: StoredLeash) -> Any:
        said: dict[str, Any] = {}
        said["pinned"] = await client.post(f"{PATH}/supervision/pin", headers=headers("u_admin"))
        said["early"] = await client.post(f"{PATH}/supervision/review", headers=headers("u_admin"))
        started = datetime.now(UTC) - timedelta(days=31)
        await store.write_pin(
            ShadowPin(
                agent_id=AGENT,
                pinned_at=started,
                review_due_at=started + SHADOW_REVIEW_PERIOD,
            ),
            PinOutcome.PINNED,
            by="u_admin",
            counts=None,
            at=datetime.now(UTC),
            ent_hash="0" * 32,
            trace_id="t-due",
        )
        said["reviewed"] = await client.post(
            f"{PATH}/supervision/review", headers=headers("u_admin")
        )
        said["leash"] = (await client.get(f"{PATH}/leash", headers=headers("u_admin"))).json()
        return said, started

    said, started = pressed(database, act)
    assert said["pinned"].json()["outcome"] == "pinned", said["pinned"].text
    assert said["early"].status_code == 409
    assert said["early"].json()["message"] == NOT_DUE_YET
    assert said["reviewed"].json()["outcome"] == "extended"
    supervision = said["leash"]["supervision"]
    assert (supervision["outcome"], supervision["held"], supervision["due"]) == (
        "extended",
        True,
        False,
    )
    assert datetime.fromisoformat(supervision["pinned_at"]) == started
    assert supervision["reviewed"] == 0
