"""Stored workflows over HTTP: who writes, who assigns, who runs, and what a run keeps.

Driven through the real application with signed-in people and a stub where the pool is, borrowing
the agents and people of `tests/unit/test_coordination_routes.py`. The store is in memory and
records every write; the door a run's steps go through is a script (the real one is held to the
gate in the last tests here, over the product's own registry and a record source).

Task ids: M17.6.1, M17.6.2, M17.6.7, M17.6.8, M17.7.7
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from fastapi.testclient import TestClient

import brain.workflow_routes as routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
from brain.api import API_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.knowledge.rows import ID_KEY, RowQuery
from brain.knowledge.visibility import Visibility
from brain.ops import workflow_store
from brain.orchestration.workflow import read_definition
from brain.orchestration.workflow_run import (
    Cause,
    RunRecord,
    StepCall,
    StepRefusedError,
    StepResult,
)
from brain.tools.startup import build_registry
from tests.fixtures.console_http import console_client, get, headers, no_audience_extras
from tests.unit.test_coordination_routes import GRANTS, LEAD, Lifecycles, _answer

NOW = datetime(2999, 1, 1, tzinfo=UTC)

DEFINITION: dict[str, Any] = {
    "name": "Monthly report",
    "steps": [
        {
            "id": "fetch",
            "kind": "tool",
            "target": "alpha.read_beta",
            "outputs": [{"name": "n", "kind": "integer", "path": "n"}],
            "on_failure": "continue",
        },
        {
            "id": "later",
            "kind": "tool",
            "target": "alpha.read_beta",
            "after": ["fetch"],
            "arguments": {"count": {"$ref": "fetch.n"}},
        },
    ],
}


@dataclass
class Kept:
    """`Workflows` in memory."""

    versions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    assigned_to: dict[str, tuple[str, ...]] = field(default_factory=dict)
    writes: list[tuple[Any, ...]] = field(default_factory=list)
    finished: list[tuple[RunRecord, str]] = field(default_factory=list)

    async def save(self, *, workflow_id: str, raw: Any, by: str) -> int:
        read_definition(raw)
        self.versions.setdefault(workflow_id, []).append(raw)
        self.writes.append(("save", workflow_id, by))
        return len(self.versions[workflow_id])

    async def latest(self, workflow_id: str) -> workflow_store.Stored | None:
        held = self.versions.get(workflow_id)
        if not held:
            return None
        return workflow_store.Stored(
            workflow_id, len(held), read_definition(held[-1]), "u_admin", NOW
        )

    async def listing(self) -> tuple[workflow_store.Listed, ...]:
        return tuple(
            workflow_store.Listed(key, len(held), str(held[-1]["name"]))
            for key, held in sorted(self.versions.items())
        )

    async def assigned(self, agent_id: str) -> tuple[str, ...]:
        return self.assigned_to.get(agent_id, ())

    async def assign(self, *, agent_id: str, workflow_id: str, by: str) -> bool:
        now = self.assigned_to.get(agent_id, ())
        if workflow_id in now:
            return False
        self.writes.append(("assign", agent_id, workflow_id, by))
        self.assigned_to[agent_id] = (*now, workflow_id)
        return True

    async def unassign(self, *, agent_id: str, workflow_id: str, by: str) -> bool:
        now = self.assigned_to.get(agent_id, ())
        if workflow_id not in now:
            return False
        self.writes.append(("unassign", agent_id, workflow_id, by))
        self.assigned_to[agent_id] = tuple(one for one in now if one != workflow_id)
        return True

    async def finish(self, record: RunRecord, *, at: datetime, by: str) -> workflow_store.Finished:
        self.finished.append((record, by))
        return workflow_store.Finished(candidates=())

    async def runs(self, workflow_id: str | None) -> tuple[workflow_store.KeptRun, ...]:
        return ()


class ScriptedDoor:
    """The door a run's steps go through: records what it was handed and answers from a script."""

    built: ClassVar[list[tuple[Any, Any, Any]]] = []
    calls: ClassVar[list[StepCall]] = []
    script: ClassVar[dict[str, Any]] = {}
    writes_offered = False

    def __init__(self, request: Any, asked: Any, record: AgentRecord) -> None:
        ScriptedDoor.built.append((request, asked, record))

    async def carry_out(self, call: StepCall) -> StepResult:
        ScriptedDoor.calls.append(call)
        given = ScriptedDoor.script[call.step_id]
        if isinstance(given, Exception):
            raise given
        return StepResult(records=(dict(given),))


@dataclass
class Served:
    client: TestClient
    kept: Kept

    def save(self, pid: str, workflow_id: str = "monthly", definition: Any = None) -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.WORKFLOWS_PATH}",
            json={"workflow_id": workflow_id, "definition": definition or DEFINITION},
            headers=headers(pid),
        )

    def assign(self, pid: str, agent: str = LEAD, workflow: str = "monthly") -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.ASSIGNED_PATH.format(agent_id=agent)}",
            json={"workflow_id": workflow},
            headers=headers(pid),
        )

    def unassign(self, pid: str, agent: str = LEAD, workflow: str = "monthly") -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.UNASSIGNED_PATH.format(agent_id=agent)}",
            json={"workflow_id": workflow},
            headers=headers(pid),
        )

    def run(self, pid: str, agent: str = LEAD, workflow: str = "monthly") -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.RUN_PATH.format(agent_id=agent)}",
            json={"workflow_id": workflow},
            headers=headers(pid),
        )


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    ScriptedDoor.built, ScriptedDoor.calls = [], []
    ScriptedDoor.script = {"fetch": {"n": 4}, "later": {}}
    monkeypatch.setattr(routes, "GateDoor", ScriptedDoor)
    with console_client(GRANTS, routers=(routes.router,)) as (client, stub):
        stub.answerers.append(no_audience_extras)
        stub.answerers.append(_answer)
        kept = Kept()
        state = client.app.state  # type: ignore[attr-defined]
        state.agent_lifecycles = Lifecycles()
        state.workflows = kept
        state.stored_workflows_on = True
        yield Served(client, kept)


def _told(reply: Any) -> dict[str, Any]:
    return {k: v for k, v in reply.json().items() if k != "trace_id"}


# --------------------------------------------------------------------------- writing
def test_the_authority_saves_a_workflow_as_the_next_version_and_reads_it_back(
    served: Served,
) -> None:
    """Delete this and saving writes nothing, writes as somebody else, or overwrites a version."""
    first = served.save("u_admin")
    assert first.status_code == 201 and first.json()["version"] == 1
    assert (first.json()["name"], first.json()["steps"]) == ("Monthly report", 2)
    assert served.save("u_admin").json()["version"] == 2
    assert served.kept.writes[0] == ("save", "monthly", "u_admin")
    page = get(
        served.client,
        "u_admin",
        f"{API_PREFIX}{routes.WORKFLOW_PATH.format(workflow_id='monthly')}",
    )
    body = page.json()
    assert body["version"] == 2 and body["definition"]["steps"][1]["arguments"] == {
        "count": {"$ref": "fetch.n"}
    }
    listing = get(served.client, "u_admin", f"{API_PREFIX}{routes.WORKFLOWS_PATH}").json()
    assert listing["workflows"] == [
        {"workflow_id": "monthly", "version": 2, "name": "Monthly report"}
    ]


def test_a_reader_without_the_authority_is_answered_as_for_a_screen_that_is_not_there(
    served: Served,
) -> None:
    """Delete this and a colleague can write, list or read how agents are used."""
    path = f"{API_PREFIX}{routes.WORKFLOWS_PATH}"
    assert served.save("u_narrow").status_code == 404
    assert get(served.client, "u_narrow", path).status_code == 404
    assert served.kept.versions == {}
    served.save("u_admin")
    missing = get(served.client, "u_admin", f"{path}/no_such")
    other = get(served.client, "u_narrow", f"{path}/monthly")
    assert missing.status_code == other.status_code == 404
    assert _told(missing) == _told(other)


def test_a_definition_the_reader_refuses_is_told_with_its_reasons_and_writes_nothing(
    served: Served,
) -> None:
    """Delete this and a malformed workflow is stored, or refused without saying why."""
    bad = {
        "name": "x",
        "steps": [
            {
                "id": "a",
                "kind": "tool",
                "target": "alpha.read_beta",
                "outputs": [{"name": "t", "kind": "text", "path": "t"}],
            }
        ],
    }
    reply = served.save("u_admin", definition=bad)
    assert reply.status_code == 409
    assert "prose is not a kind" in reply.json()["sentence"]
    assert served.kept.versions == {}


def test_a_workflow_id_that_is_not_a_slug_is_not_saved(served: Served) -> None:
    """Delete this and an id that is a path or a sentence becomes a key."""
    assert served.save("u_admin", workflow_id="Has Spaces").status_code == 422
    assert served.kept.versions == {}


# ------------------------------------------------------------------------- assigning
def test_the_authority_over_an_agent_assigns_and_withdraws_a_workflow(served: Served) -> None:
    """Delete this and an agent runs a workflow nobody gave it, or one cannot be taken back."""
    served.save("u_admin")
    done = served.assign("u_admin")
    assert done.status_code == 200 and done.json()["workflows"] == ["monthly"]
    assert served.kept.writes[-1] == ("assign", LEAD, "monthly", "u_admin")
    assert served.assign("u_admin").status_code == 200
    assert [w for w in served.kept.writes if w[0] == "assign"] == [served.kept.writes[-1]]
    gone = served.unassign("u_admin")
    assert gone.status_code == 200 and gone.json()["workflows"] == []
    nothing = served.unassign("u_admin")
    assert nothing.status_code == 409 and nothing.json()["sentence"] == routes.NOTHING_TO_WITHDRAW


def test_a_workflow_that_does_not_exist_cannot_be_assigned_and_a_colleague_cannot_assign(
    served: Served,
) -> None:
    """Delete this and an agent is assigned a workflow that is not there, or by anyone."""
    reply = served.assign("u_admin", workflow="no_such")
    assert reply.status_code == 409 and reply.json()["sentence"] == routes.NO_WORKFLOW_TO_ASSIGN
    served.save("u_admin")
    assert served.assign("u_narrow").status_code == 404
    assert served.kept.assigned_to == {}


def test_only_those_who_answer_for_an_agent_are_told_what_it_may_run(served: Served) -> None:
    """Delete this and a colleague learns which workflows an agent is wired to, or that any are."""
    served.save("u_admin")
    served.assign("u_admin")
    path = f"{API_PREFIX}{routes.ASSIGNED_PATH.format(agent_id=LEAD)}"
    shown = get(served.client, "u_admin", path).json()
    assert shown["names_shown"] and shown["workflows"] == ["monthly"] and shown["may_change"]
    other = get(served.client, "u_narrow", path).json()
    served.kept.assigned_to.clear()
    bare = get(served.client, "u_narrow", path).json()
    assert other == bare and other["workflows"] == [] and other["names_shown"] is False


# ---------------------------------------------------------------------------- running
def test_nothing_runs_while_the_switch_is_off(served: Served) -> None:
    """Delete this and a workflow runs on an install that never turned this on."""
    served.save("u_admin")
    served.assign("u_admin")
    served.client.app.state.stored_workflows_on = False  # type: ignore[attr-defined]
    reply = served.run("u_narrow")
    assert reply.status_code == 409 and reply.json()["sentence"] == routes.NOT_SWITCHED_ON
    assert ScriptedDoor.built == []


def test_an_agent_not_assigned_the_workflow_and_a_workflow_that_is_not_there_are_one_answer(
    served: Served,
) -> None:
    """Delete this and a request can ask which workflows exist, and the refusal comes after a step.

    The sibling shows the same request running once the agent is assigned.
    """
    served.save("u_admin")
    unassigned = served.run("u_narrow")
    missing = served.run("u_narrow", workflow="no_such")
    assert unassigned.status_code == missing.status_code == 409
    assert _told(unassigned) == _told(missing)
    assert ScriptedDoor.built == [] and served.kept.finished == []
    served.assign("u_admin")
    assert served.run("u_narrow").status_code == 200


def test_an_agent_the_asker_cannot_start_is_the_answer_a_missing_one_gets(served: Served) -> None:
    """Delete this and a run enumerates the agents in other departments."""
    served.save("u_admin")
    served.assign("u_admin")
    refused = served.run("u_elsewhere")
    missing = served.run("u_elsewhere", agent="no_such_desk")
    assert refused.status_code == missing.status_code == 404
    assert _told(refused) == _told(missing)


def test_a_run_goes_through_the_door_as_the_asker_and_is_kept_with_one_trace(
    served: Served,
) -> None:
    """Delete this and a run is not run as the person who asked, or leaves no trace.

    The door is built with the asker and the agent and nothing else, each step carries the same key
    on every attempt, and the run is finished once, in the asker's name.
    """
    served.save("u_admin")
    served.assign("u_admin")
    reply = served.run("u_narrow")
    assert reply.status_code == 200
    body = reply.json()
    assert (body["workflow_id"], body["version"], body["agent_id"]) == ("monthly", 1, LEAD)
    assert body["outcome"] == "success" and body["failed_step"] is None
    assert [(s["step_id"], s["status"]) for s in body["steps"]] == [
        ("fetch", "ok"),
        ("later", "ok"),
    ]
    ((_, asked, record),) = ScriptedDoor.built
    assert asked.caller.principal.id == "u_narrow" and record.agent_id == LEAD
    assert [c.arguments for c in ScriptedDoor.calls] == [{}, {"count": 4}]
    ((kept, by),) = served.kept.finished
    assert by == "u_narrow" and kept.run_id == body["run_id"]


def test_a_failed_step_is_named_in_the_answer_and_a_stop_ends_the_run(served: Served) -> None:
    """Delete this and a failure is reported as success or names nothing."""
    served.save("u_admin")
    served.assign("u_admin")
    ScriptedDoor.script = {"fetch": StepRefusedError(), "later": {}}
    body = served.run("u_narrow").json()
    assert body["outcome"] == "failure" and body["failed_step"] == "fetch"
    assert [s["cause"] for s in body["steps"]] == [Cause.REFUSED.value, Cause.INPUT_MISSING.value]


# -------------------------------------------------------------- the door is the gate's
class Rows:
    """A record source returning one row whatever the statement asked for."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        return (
            {ID_KEY: "p1", "sku": "WEB-1", "name": "Hosting", "sell_price": "99", "cost": "40"},
        )


def _door_world(ceiling_columns: Sequence[str]) -> tuple[routes.GateDoor, str, Any]:
    registry = build_registry(source="local", records=Rows())
    tool = next(d.name for d in registry.definitions() if d.entity == "price_list")
    columns = (
        "read:price_list",
        "read:price_list.sku",
        "read:price_list.name",
        "read:price_list.sell_price",
        "read:price_list.cost",
    )
    person = Principal(
        id="u_asker", kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="A"
    )
    asked = SimpleNamespace(
        caller=SimpleNamespace(principal=person),
        reach=EntitlementSet(
            principal_id="u_asker",
            grants=tuple(Grant(capability=Capability(value=c), scope=Scope()) for c in columns),
        ),
        channel=Channel.CONSOLE,
        now=NOW,
    )
    record = AgentRecord(
        agent_id="reporter",
        display_name="Reporter",
        persona="Reports.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=tuple(Capability(value=c) for c in ceiling_columns),
            allowed_tools=frozenset({tool}),
        ),
        created_by="u_steward",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tools=registry)))
    return routes.GateDoor(cast(Any, request), cast(Any, asked), record), tool, record


def _call(tool: str, arguments: dict[str, Any] | None = None) -> StepCall:
    from brain.orchestration.workflow import StepKind

    return StepCall("r", "s", StepKind.TOOL, tool, arguments or {"limit": 5}, "r:s", 1)


def test_a_step_receives_only_the_asker_narrowed_by_the_agent() -> None:
    """Delete this and a workflow step reaches what its agent's ceiling took from the asker.

    The asker holds every column; the agent's ceiling names sku and name. The records the step gets
    hold those two and neither the price nor the cost, which were fetched and withheld.
    """
    import asyncio

    door, tool, _ = _door_world(("read:price_list", "read:price_list.sku", "read:price_list.name"))
    result = asyncio.run(door.carry_out(_call(tool)))
    (record,) = result.records
    assert record["sku"] == "WEB-1" and record["name"] == "Hosting"
    assert "sell_price" not in record and "cost" not in record
    assert "99" not in repr(result) and "40" not in repr(result)


def test_a_tool_the_agent_may_not_call_and_a_tool_that_does_not_exist_are_one_refusal() -> None:
    """Delete this and a step can tell which tools exist by what it is refused with."""
    import asyncio

    door, tool, _ = _door_world(("read:price_list", "read:price_list.sku"))
    errors = []
    for name in ("nothing.read_here", "price_list", "x" * 90):
        with pytest.raises(StepRefusedError) as raised:
            asyncio.run(door.carry_out(_call(name)))
        errors.append(type(raised.value))
    assert len(set(errors)) == 1
    assert asyncio.run(door.carry_out(_call(tool))).records


def test_a_step_cannot_name_a_parameter_a_handler_takes_as_wiring() -> None:
    """Delete this and a step can set the entitlement its tool runs with."""
    import asyncio

    door, tool, _ = _door_world(("read:price_list", "read:price_list.sku"))
    with pytest.raises(StepRefusedError):
        asyncio.run(door.carry_out(_call(tool, {"entitlement": "everything"})))


def test_the_door_offers_no_writes_until_a_held_action_has_been_shown_to_reach_a_person() -> None:
    """Delete this and a workflow step that changes something is run with nobody holding it."""
    door, _, record = _door_world(("read:price_list",))
    assert door.writes_offered is False
    assert entitlement_ceiling(record).principal_id.startswith("agent:")
