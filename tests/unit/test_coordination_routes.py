"""A coordinating agent over HTTP: who may call whom, who is told, and a request split between them.

Driven through the real application with signed-in people and a stub where the pool is, as
`tests/unit/test_agent_audience_routes.py` is. The links and the fan-out grant are held by an
in-memory store that records every write it was asked for; the model that splits a request is a
script; the function that answers a specialist's question is replaced by one that records what it
was handed (the person, the reach, the lenses, the question) and returns a scripted answer. That the
rows reach PostgreSQL under their row policies, and that a plan is split and run on a real install,
are the install checks in `brain.ops.acceptance_checks_coordination`.

Task ids: M18.1.1, M18.5.1, M18.5.3, M18.6.2
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

import brain.coordination_routes as routes
from brain.agent_lifecycle_routes import FoundAgent
from brain.agent_routes import record_of
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.lane import Lane
from brain.core.scope import Scope
from brain.gate.answer import Answered
from brain.knowledge.visibility import Visibility
from brain.models.driver import DriverMessage, DriverResponse, TokenUsage
from brain.models.metering import Meter
from brain.ops.halt import NOTHING_HALTED
from brain.orchestration.coordinator import Coordinated
from brain.tables.agent import AgentRow
from brain.tables.coordinated_run import CoordinatedRunRow
from tests.fixtures.console_http import Stub, console_client, get, headers, no_audience_extras
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row

LEAD = "lead_desk"
WEB_ONE = "web_one"
WEB_TWO = "web_two"
FINANCE = "finance_desk"
PRIVATE = "private_desk"
STRANGER = "stranger_desk"

READ = "read:site.score"

#: `u_admin` (web) holds the lifecycle authority everywhere; `u_narrow` (web) is the steward of
#: `private_desk` and holds nothing, and is who asks; `u_elsewhere` (finance) holds nothing here.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=Capability(value=READ), scope=Scope.unrestricted()),),
    "u_wide": (),
    "u_none": (),
    "u_elsewhere": (),
    "u_prefix": (),
}

ROWS: Mapping[str, AgentRow] = {
    LEAD: agent_row(LEAD, level=Visibility.DEPARTMENT, department="web", owner_id="u_steward"),
    WEB_ONE: agent_row(
        WEB_ONE,
        level=Visibility.DEPARTMENT,
        department="web",
        capabilities=(Capability(value=READ),),
    ),
    WEB_TWO: agent_row(
        WEB_TWO,
        level=Visibility.DEPARTMENT,
        department="web",
        capabilities=(Capability(value=READ),),
    ),
    FINANCE: agent_row(FINANCE, level=Visibility.DEPARTMENT, department="finance"),
    PRIVATE: agent_row(PRIVATE, level=Visibility.PERSONAL, owner_id="u_admin"),
}

NOW = datetime(2999, 1, 1, tzinfo=UTC)


def _answer(statement: Any) -> Result | None:
    """The one agent row a request asked for, or the kept runs."""
    if not isinstance(statement, Select):
        return None
    described = statement.column_descriptions
    entity = described[0].get("entity")
    if entity is AgentRow and len(described) == 1:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    if entity is CoordinatedRunRow:
        return Result(Stored.runs)
    return None


class Stored:
    """The kept runs a listing reads."""

    runs: ClassVar[list[CoordinatedRunRow]] = []


class Lifecycles:
    """The lifecycle authority's read of an agent, and nothing else."""

    async def agent(self, agent_id: str) -> FoundAgent | None:
        row = ROWS.get(agent_id)
        record = None if row is None else record_of(row)
        return (
            None if record is None else FoundAgent(record=record, install=None, effective_hash=None)
        )

    async def version(self, *_: Any, **__: Any) -> None:
        raise AssertionError("coordination reads no template version")

    async def live_principal(self, *_: Any, **__: Any) -> None:
        raise AssertionError("coordination checks no person")

    async def change(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("coordination changes no agent row")

    async def widen(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("coordination changes no agent row")

    async def create(self, *_: Any, **__: Any) -> None:
        raise AssertionError("coordination makes no agent")

    async def change_channels(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("coordination changes no channel")


@dataclass
class Links:
    """`Coordination` in memory: who may call whom, and every write asked of it."""

    held: dict[str, tuple[str, ...]] = field(default_factory=dict)
    fan: set[str] = field(default_factory=set)
    writes: list[tuple[Any, ...]] = field(default_factory=list)

    async def callees(self, agent_id: str) -> tuple[str, ...]:
        return self.held.get(agent_id, ())

    async def fan_out(self, agent_id: str) -> bool:
        return agent_id in self.fan

    async def allow(self, *, coordinator_id: str, callee_id: str, by: str) -> bool:
        now = self.held.get(coordinator_id, ())
        if callee_id in now:
            return False
        self.writes.append(("allow", coordinator_id, callee_id, by))
        self.held[coordinator_id] = (*now, callee_id)
        return True

    async def withdraw(self, *, coordinator_id: str, callee_id: str, by: str) -> bool:
        now = self.held.get(coordinator_id, ())
        if callee_id not in now:
            return False
        self.writes.append(("withdraw", coordinator_id, callee_id, by))
        self.held[coordinator_id] = tuple(one for one in now if one != callee_id)
        return True

    async def set_fan_out(self, *, agent_id: str, enabled: bool, by: str) -> bool:
        if enabled == (agent_id in self.fan):
            return False
        self.writes.append(("fan_out", agent_id, enabled, by))
        (self.fan.add if enabled else self.fan.discard)(agent_id)
        return True


class Planner:
    """The model that splits a request: a scripted reply, and what it was asked."""

    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.asked: list[tuple[DriverMessage, ...]] = []

    async def complete(
        self,
        messages: tuple[DriverMessage, ...],
        *,
        lane: Lane,
        meter: Meter,
        trace_id: str,
        tier: Any = None,
        max_output_tokens: int | None = None,
        categories: tuple[Any, ...] = (),
    ) -> DriverResponse:
        self.asked.append(messages)
        assert self.reply is not None
        return DriverResponse(
            deployment_id="d",
            model="m",
            text=self.reply,
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            finish_reason="stop",
        )


class Keeper:
    """`RunKeeper` in memory."""

    def __init__(self) -> None:
        self.kept: list[tuple[Coordinated, str, str]] = []

    async def keep(self, ran: Coordinated, *, coordinator_id: str, at: datetime, by: str) -> None:
        self.kept.append((ran, coordinator_id, by))


@dataclass
class Asked:
    """What `answered_for` was handed for one specialist."""

    agent: str
    question: str
    reach: Any
    lenses: tuple[Any, ...]
    principal: str


@dataclass
class Served:
    client: TestClient
    stub: Stub
    links: Links
    keeper: Keeper
    answers: list[Asked]
    planner: Planner

    def run(self, pid: str, ask: str = "Review the client's site", coordinator: str = LEAD) -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.RUNS_PATH}",
            json={"coordinator_id": coordinator, "ask": ask},
            headers=headers(pid),
        )

    def view(self, pid: str, agent_id: str) -> Any:
        return get(
            self.client, pid, f"{API_PREFIX}{routes.COORDINATION_PATH.format(agent_id=agent_id)}"
        )

    def allow(self, pid: str, agent_id: str, callee: str) -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.CALLEES_PATH.format(agent_id=agent_id)}",
            json={"callee_id": callee},
            headers=headers(pid),
        )

    def withdraw(self, pid: str, agent_id: str, callee: str) -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.CALLEE_REMOVALS_PATH.format(agent_id=agent_id)}",
            json={"callee_id": callee},
            headers=headers(pid),
        )

    def fan_out(self, pid: str, agent_id: str, enabled: bool) -> Any:
        return self.client.post(
            f"{API_PREFIX}{routes.FAN_OUT_PATH.format(agent_id=agent_id)}",
            json={"enabled": enabled},
            headers=headers(pid),
        )


def _told(reply: Any) -> dict[str, Any]:
    """A refusal's body without the trace id, which is the one thing that differs between two."""
    return {k: v for k, v in reply.json().items() if k != "trace_id"}


def _plan(*subtasks: dict[str, Any]) -> str:
    return json.dumps({"subtasks": list(subtasks)})


def _subtask(subtask_id: str, callee: str, **over: Any) -> dict[str, Any]:
    return {
        "subtask_id": subtask_id,
        "callee": callee,
        "objective": f"Find the site score called {subtask_id}",
        "output": [{"name": "score", "kind": "integer"}],
        "depends_on": [],
    } | over


TWO_AT_ONCE = _plan(_subtask("one", WEB_ONE), _subtask("two", WEB_TWO))


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    answers: list[Asked] = []

    async def answered(
        request: Any, recorder: Any, answering: Any, question: Any, **_: Any
    ) -> Answered:
        answers.append(
            Asked(
                agent=question.agent,
                question=question.question,
                reach=answering.reach,
                lenses=answering.lenses,
                principal=answering.principal.id,
            )
        )
        return Answered(
            frames=("event: text",),
            composed=cast(Any, object()),
            text=json.dumps({"score": len(answers)}),
        )

    async def not_halted(_: Any) -> Any:
        return NOTHING_HALTED

    monkeypatch.setattr(routes, "answered_for", answered)
    monkeypatch.setattr(routes, "read_state", not_halted)
    Stored.runs = []
    with console_client(GRANTS, routers=(routes.router,)) as (client, stub):
        stub.answerers.append(no_audience_extras)
        stub.answerers.append(_answer)
        links = Links(held={LEAD: (WEB_ONE, WEB_TWO, FINANCE)})
        keeper = Keeper()
        planner = Planner(TWO_AT_ONCE)
        state = client.app.state  # type: ignore[attr-defined]
        state.agent_lifecycles = Lifecycles()
        state.agent_coordination = links
        state.coordinated_run_keeper = keeper
        state.planner_calls = planner
        state.multi_agent_coordination_on = True
        yield Served(client, stub, links, keeper, answers, planner)


# ------------------------------------------------------------------ who may change it
def test_an_administrator_allows_a_callee_and_the_write_is_in_their_name(served: Served) -> None:
    """Delete this and allowing a callee writes nothing, or writes as somebody else.

    The sibling checks below show the same call refused, so this is not a route that allows all.
    """
    reply = served.allow("u_admin", WEB_ONE, WEB_TWO)
    assert reply.status_code == 200
    assert served.links.writes == [("allow", WEB_ONE, WEB_TWO, "u_admin")]
    assert [one["agent_id"] for one in reply.json()["callees"]] == [WEB_TWO]
    again = served.allow("u_admin", WEB_ONE, WEB_TWO)
    assert again.status_code == 200
    assert len(served.links.writes) == 1


def test_a_reader_without_the_authority_gets_the_answer_a_missing_agent_gets(
    served: Served,
) -> None:
    """Delete this and a colleague can tell which agents exist by trying to link them."""
    refused = served.allow("u_narrow", LEAD, WEB_ONE)
    missing = served.allow("u_narrow", "no_such_desk", WEB_ONE)
    assert refused.status_code == missing.status_code == 404
    assert _told(refused) == _told(missing)
    assert served.links.writes == []


@pytest.mark.parametrize(
    ("callee", "why"),
    [
        (LEAD, routes.AN_AGENT_DOES_NOT_CALL_ITSELF),
        (FINANCE, routes.NO_AGENT_TO_CALL),
        ("no_such_desk", routes.NO_AGENT_TO_CALL),
        (PRIVATE, routes.A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER),
    ],
)
def test_a_callee_that_cannot_be_allowed_is_told_why_in_one_sentence(
    served: Served, callee: str, why: str
) -> None:
    """Delete this and an administrator can link an agent they cannot see, themselves or a
    personal agent. An agent they cannot see and one that is not there get the same sentence."""
    reply = served.allow("u_admin", LEAD, callee)
    assert reply.status_code == 409
    assert reply.json()["sentence"] == why
    assert served.links.writes == []


def test_a_link_is_withdrawn_in_the_callers_name_and_withdrawing_nothing_is_said(
    served: Served,
) -> None:
    """Delete this and a link cannot be taken back, or taking back what is not there passes."""
    served.links.held[WEB_ONE] = (WEB_TWO,)
    done = served.withdraw("u_admin", WEB_ONE, WEB_TWO)
    assert done.status_code == 200
    assert served.links.writes == [("withdraw", WEB_ONE, WEB_TWO, "u_admin")]
    nothing = served.withdraw("u_admin", WEB_ONE, WEB_TWO)
    assert nothing.status_code == 409
    assert nothing.json()["sentence"] == routes.NOTHING_TO_WITHDRAW


def test_fan_out_is_granted_and_taken_back_by_the_authority_only(served: Served) -> None:
    """Delete this and anybody can let an agent run its specialists at the same time."""
    on = served.fan_out("u_admin", LEAD, True)
    assert on.status_code == 200 and on.json()["fan_out_enabled"] is True
    assert served.links.writes == [("fan_out", LEAD, True, "u_admin")]
    assert served.fan_out("u_narrow", LEAD, False).status_code == 404
    assert LEAD in served.links.fan
    off = served.fan_out("u_admin", LEAD, False)
    assert off.json()["fan_out_enabled"] is False


# ----------------------------------------------------------------------- who is told
def test_only_those_who_answer_for_a_coordinator_are_told_what_it_may_call(
    served: Served,
) -> None:
    """Delete this and a colleague learns which agents a coordinator is wired to.

    The steward and the administrator see the specialists the reader could see anyway (the
    finance agent is left out for a reader in web), and everyone else gets a body that does not
    change with what is stored: the same for a coordinator with links and one without.
    """
    served.links.fan.add(LEAD)
    shown = served.view("u_admin", LEAD).json()
    assert shown["names_shown"] is True
    assert [one["agent_id"] for one in shown["callees"]] == [WEB_ONE, WEB_TWO]
    assert shown["fan_out_enabled"] is True
    other = served.view("u_narrow", LEAD).json()
    served.links.held.pop(LEAD)
    served.links.fan.clear()
    bare = served.view("u_narrow", LEAD).json()
    assert other == bare
    assert other["names_shown"] is False and other["callees"] == []
    assert other["fan_out_enabled"] is False


# ------------------------------------------------------------------------- running
def test_nothing_is_asked_of_a_model_while_the_switch_is_off(served: Served) -> None:
    """Delete this and a request is sent to a provider on an install that never turned this on."""
    served.client.app.state.multi_agent_coordination_on = False  # type: ignore[attr-defined]
    reply = served.run("u_narrow")
    assert reply.status_code == 409
    assert reply.json()["sentence"] == routes.NOT_SWITCHED_ON
    assert served.planner.asked == [] and served.answers == []


def test_a_coordinator_the_asker_cannot_start_is_the_answer_a_missing_one_gets(
    served: Served,
) -> None:
    """Delete this and a request enumerates the coordinators in other departments."""
    refused = served.run("u_elsewhere")
    missing = served.run("u_elsewhere", coordinator="no_such_desk")
    assert refused.status_code == missing.status_code == 404
    assert _told(refused) == _told(missing)
    assert served.planner.asked == []


def test_a_coordinator_with_no_specialists_starts_nothing_and_asks_no_model(
    served: Served,
) -> None:
    """Delete this and an agent nobody linked costs a model call to find out."""
    served.links.held.clear()
    reply = served.run("u_narrow")
    assert reply.status_code == 409
    assert reply.json()["sentence"] == routes.NO_SPECIALISTS_HERE
    assert served.planner.asked == []


def test_without_a_model_the_request_is_not_split_and_it_is_said(served: Served) -> None:
    """Delete this and a process with no provider fails with a stack trace."""
    served.client.app.state.planner_calls = None  # type: ignore[attr-defined]
    served.client.app.state.models = None  # type: ignore[attr-defined]
    reply = served.run("u_narrow")
    assert reply.status_code == 409
    assert reply.json()["sentence"] == routes.NO_MODEL_HERE


def test_the_model_is_shown_the_request_and_only_the_specialists_the_asker_may_start(
    served: Served,
) -> None:
    """Delete this and the planner is offered an agent the asker cannot start, which then tells
    the asker it exists. The finance agent is linked and is not offered to a reader in web."""
    served.run("u_narrow", ask="Review the client's site")
    (messages,) = served.planner.asked
    sent = json.loads(messages[1].content)
    assert sent["request"] == "Review the client's site"
    assert [one["id"] for one in sent["specialists"]] == [WEB_ONE, WEB_TWO]
    assert set(sent) == {"request", "specialists"}


def test_a_plan_that_cannot_be_used_starts_nothing(served: Served) -> None:
    """Delete this and a malformed or over-reaching plan is partly run."""
    for bad in (
        "not json",
        _plan(_subtask("one", FINANCE)),
        _plan(_subtask("one", WEB_ONE, cost=5)),
        _plan(_subtask("one", WEB_ONE, output=[{"name": "note", "kind": "text"}])),
    ):
        served.planner.reply = bad
        reply = served.run("u_narrow")
        assert reply.status_code == 409
        assert reply.json()["sentence"] == routes.THE_PLAN_COULD_NOT_BE_USED
    assert served.answers == [] and served.keeper.kept == []


def test_a_plan_is_run_in_turn_when_fan_out_was_never_enabled_and_the_reason_is_kept(
    served: Served,
) -> None:
    """Delete this and a run that was not allowed to fan out does, or loses why it did not."""
    reply = served.run("u_narrow")
    assert reply.status_code == 200
    body = reply.json()
    assert body["mode"] == "sequential"
    assert body["why"] == ["fan_out_not_enabled"]
    assert [one.agent for one in served.answers] == [WEB_ONE, WEB_TWO]
    assert {one["status"] for one in body["children"]} == {"delivered"}
    assert body["merged"]["complete"] is True
    ((kept, coordinator, by),) = served.keeper.kept
    assert (coordinator, by) == (LEAD, "u_narrow")
    assert [one.value for one in kept.why] == ["fan_out_not_enabled"]


def test_a_plan_is_run_together_when_it_was_allowed_and_the_gate_agrees(
    served: Served,
) -> None:
    """Delete this and enabling fan-out changes nothing, because nothing ever runs together."""
    served.links.fan.add(LEAD)
    served.planner.reply = _plan(*(_subtask(f"s{i}", WEB_ONE) for i in range(4)))
    body = served.run("u_narrow").json()
    assert body["mode"] == "parallel"
    assert body["why"] == []
    assert body["gate"]["verdict"] == "parallel"
    assert len(served.answers) == 4


def test_each_specialist_is_asked_as_the_asker_at_a_reach_narrowed_by_every_lens(
    served: Served,
) -> None:
    """Delete this and a specialist is asked at the asker's whole reach, or with the lenses left
    off so its first tool call gives back what the coordinator took away. The question carries the
    objective and the shape of the answer and names no capability."""
    served.run("u_narrow")
    first = served.answers[0]
    assert first.principal == "u_narrow"
    assert first.reach.principal_id == "u_narrow"
    assert len(first.lenses) == 3
    assert [one.principal_id.split(":")[0] for one in first.lenses] == ["agent", "agent", "subtask"]
    assert "Find the site score called one" in first.question
    assert "read:" not in first.question and "u_narrow" not in first.question
    assert '"score" (a whole number)' in first.question


def test_a_specialist_that_is_turned_away_is_a_stated_gap_and_not_an_error(
    served: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and one refused specialist fails the whole request with a server error."""

    async def refused(*_: Any, **__: Any) -> str:
        return "not an Answered"

    monkeypatch.setattr(routes, "answered_for", refused)
    reply = served.run("u_narrow")
    assert reply.status_code == 200
    body = reply.json()
    assert {one["status"] for one in body["children"]} == {"refused"}
    assert body["merged"]["complete"] is False
    assert body["merged"]["notice"] != ""


def test_the_runs_kept_are_told_to_the_authority_and_to_nobody_else(served: Served) -> None:
    """Delete this and any reader can list how every coordinated run went."""
    path = f"{API_PREFIX}{routes.RUNS_PATH}"
    assert get(served.client, "u_narrow", path).status_code == 404
    page = get(served.client, "u_admin", path)
    assert page.status_code == 200
    assert page.json() == {"runs": [], "switched_on": True}
