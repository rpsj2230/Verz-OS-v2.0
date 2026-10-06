"""One entity's figures over HTTP: who is answered, who gets the 404 a missing name gets, and that
the figures a reader is given are over rows they may read.

Driven through the real application with signed-in people and a stub where the pool is. The stub
answers each statement by the columns it selects and **evaluates the reader's predicate from the
statement's own bound parameters** (the principal on the narrower basis, `FALSE` for an entity the
reader holds no read of), so a route that stopped composing the predicate would be caught here and
not agreed with. The database tests at the bottom run the same statements against PostgreSQL.

Every refusal is compared status to status and message to message with the answer a name that
matches nothing gets, and every refusal has a sibling proving the reader in reach is answered.

Task ids: M27.15.27, M27.15.33, M11.3.4
Task ids: M39.1.3.1, M39.1.3.2, M39.1.3.3, M39.1.3.4
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.sql.selectable import Select

from brain import console_stats_routes
from brain.api import API_PREFIX
from brain.connectors.contract import HealthState
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.console.entity_stats import MAX_ACTIVITY_ROWS
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.skill_library import LibrarySkill
from brain.console.workspace import Basis
from brain.console_stats_routes import (
    AgentStatsView,
    ChannelStatsView,
    ConnectorStatsView,
    SkillStatsView,
    agent_requests,
    channel_bindings,
    channel_deliveries,
    connector_attempts,
    connector_live_reads,
    index_ids,
    router,
    skill_invocations,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel, TrafficClass
from brain.knowledge.visibility import Visibility
from brain.ops.connector_sync import SyncOutcome, SyncState
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.telemetry import RequestStatus
from brain.tables.agent import AgentRow
from brain.tables.budget import BudgetVersionRow
from brain.tables.identity import PrincipalRow
from brain.tables.spend import SpendActualRow
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_connector_routes import Records, a_connection
from tests.unit.test_skill_routes import imported

EVERYWHERE = Scope.unrestricted()
PLANES = tuple(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane)


def read(key: str) -> Capability:
    return screen(key).read.requires


def only(field: str, value: str) -> Scope:
    return Scope(clauses=(Clause(field=field, op=Op.EQ, value=value),))


#: `u_admin` reads everybody's usage, spend and people, the whole skill library, every
#: connector and every channel, and one entity of one source's rows. `u_narrow` holds each
#: screen narrowed: skills in one department, one connector, one channel, and no usage, spend
#: or people read. `u_none` holds nothing. `u_narrow` sits in web and `u_elsewhere` in finance,
#: which is who a finance department's agent is visible to. `u_wide` reads the whole skill
#: library and every connector and no usage, so a skill's runs and a source's live reads are
#: counted over their own requests alone.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        *PLANES,
        *(
            Grant(capability=read(key), scope=EVERYWHERE)
            for key in ("usage", "budget", "skills", "connectors", "people")
        ),
        Grant(capability=INSTALL_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=Capability(value="read:xero_invoice"), scope=EVERYWHERE),
    ),
    "u_narrow": (
        *PLANES,
        Grant(capability=read("skills"), scope=only("department", "web")),
        Grant(capability=read("connectors"), scope=only("connector", "hubspot")),
        Grant(capability=INSTALL_AUTHORITY, scope=only("connector", "webhook_channel")),
    ),
    "u_none": (),
    "u_elsewhere": PLANES,
    "u_wide": (
        *PLANES,
        Grant(capability=read("skills"), scope=EVERYWHERE),
        Grant(capability=read("connectors"), scope=EVERYWHERE),
    ),
}

NOW = datetime.now(UTC)
AGENT = "desk"
HIDDEN_AGENT = "finance_desk"
PERSON = TrafficClass.HUMAN_INTERACTIVE.value
SCHEDULED = TrafficClass.AUTOMATION.value


class Held:
    """What the stub database holds, answered by the columns a statement selects."""

    def __init__(self) -> None:
        self.agents: dict[str, AgentRow] = {
            AGENT: agent_row(AGENT),
            HIDDEN_AGENT: agent_row(
                HIDDEN_AGENT, level=Visibility.DEPARTMENT, department="finance"
            ),
        }
        #: (selected agent, principal, received, status, duration, traffic class). The one
        #: automation's run is a run and not a message; the sixty-day one is only in ninety days.
        self.requests: list[tuple[str, str, datetime, str, float, str]] = [
            (AGENT, "u_narrow", NOW - timedelta(days=1), "answered", 200.0, PERSON),
            (AGENT, "u_narrow", NOW - timedelta(days=10), "nothing_returned", 400.0, PERSON),
            (AGENT, "u_admin", NOW - timedelta(days=2), "answered", 800.0, SCHEDULED),
            (AGENT, "u_elsewhere", NOW - timedelta(days=3), "failed", 1600.0, PERSON),
            (AGENT, "u_admin", NOW - timedelta(days=60), "answered", 100.0, PERSON),
            (HIDDEN_AGENT, "u_elsewhere", NOW - timedelta(days=1), "answered", 50.0, PERSON),
        ]
        self.spend: list[SpendActualRow] = [
            spend_row("u_narrow", 120, NOW - timedelta(days=1)),
            spend_row("u_admin", 300, NOW - timedelta(days=12)),
            spend_row("u_admin", 80, NOW - timedelta(days=60)),
        ]
        #: The agent's monthly budget, as `ops.budget_version` would hold it, or none.
        self.budgets: list[BudgetVersionRow] = []
        #: The directory's display names, which the cost per person is drawn with.
        self.names: dict[str, str] = {"u_admin": "Admin Person", "u_narrow": "Narrow Person"}
        self.attempts: list[tuple[datetime, str]] = [
            (NOW - timedelta(days=1), "synced"),
            (NOW - timedelta(days=2), "failed"),
            (NOW - timedelta(days=20), "quota"),
        ]
        #: Kept ids per (source, entity), which a count admits only when the scope is not FALSE.
        self.kept: dict[tuple[str, str], int] = {
            ("xero", "xero_invoice"): 5,
            ("xero", "xero_contact"): 2,
        }
        self.deliveries: list[tuple[str, str, datetime]] = [
            ("inbound", "accepted", NOW - timedelta(days=1)),
            ("outbound", "sent", NOW - timedelta(days=1)),
            ("outbound", "refused", NOW - timedelta(days=8)),
        ]
        self.bound: list[str] = ["u_narrow", "u_admin", "u_elsewhere"]
        #: (agent, principal, skill, used at): `agent.skill_invocation`. The hidden agent's run
        #: is one nobody but finance may be counted over, and `other` is another skill.
        self.uses: list[tuple[str, str, str, datetime]] = [
            (AGENT, "u_admin", "triage", NOW - timedelta(days=1)),
            (AGENT, "u_wide", "triage", NOW - timedelta(days=3)),
            (AGENT, "u_elsewhere", "triage", NOW - timedelta(days=12)),
            (HIDDEN_AGENT, "u_elsewhere", "triage", NOW - timedelta(hours=2)),
            (AGENT, "u_admin", "other", NOW - timedelta(hours=1)),
        ]
        #: (source, principal, received at): request rows whose `connector` names a source.
        self.reads: list[tuple[str, str, datetime]] = [
            ("xero", "u_admin", NOW - timedelta(days=1)),
            ("xero", "u_wide", NOW - timedelta(days=2)),
            ("xero", "u_elsewhere", NOW - timedelta(days=9)),
            ("hubspot", "u_admin", NOW - timedelta(hours=1)),
        ]
        self.params: list[dict[str, Any]] = []
        self.counted: list[str] = []
        self.asked_uses: list[dict[str, Any]] = []
        self.asked_reads: list[dict[str, Any]] = []

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        described = statement.column_descriptions
        columns = [one["name"] for one in described]
        params = statement.compile().params
        self.params.append(dict(params))
        if described[0].get("entity") is AgentRow and len(described) == 1:
            if statement.whereclause is None:
                return Result(self.agents[key] for key in sorted(self.agents))
            wanted = str(statement.whereclause.right.value)
            return Result([self.agents[wanted]] if wanted in self.agents else [])
        if columns == ["principal_id", "agent_id", "used_at"]:
            principal = _bound(params, "principal_id")
            agents = _bound(params, "agent_id")
            self.asked_uses.append(dict(params))
            return Result(
                Row((who, agent, at))
                for agent, who, skill, at in self.uses
                if skill == _bound(params, "skill_name")
                and agent in agents
                and (principal is None or who == principal)
            )
        if columns == ["principal", "received_at"]:
            principal = _bound(params, "principal")
            self.asked_reads.append(dict(params))
            return Result(
                Row((who, at))
                for source, who, at in self.reads
                if source == _bound(params, "connector") and (principal is None or who == principal)
            )
        if len(described) == 2 and columns[0] != "finished_at" and columns[0] != "direction":
            # The installs of the reader's agents. None is installed in these tests.
            return Result([])
        if described[0].get("entity") is SpendActualRow:
            return Result(self.spend)
        if described[0].get("entity") is BudgetVersionRow:
            return Result(one for one in self.budgets if one.subject == _bound(params, "subject"))
        if described[0].get("entity") is PrincipalRow and len(described) == 1:
            asked_for = {str(one) for one in (_bound(params, "id") or ())}
            return Result(
                PrincipalRow(id=key, display_name=name)
                for key, name in self.names.items()
                if key in asked_for
            )
        if columns == ["principal", "received_at", "status", "duration_ms", "traffic_class"]:
            principal = _bound(params, "principal")
            return Result(
                Row((who, at, status, ms, traffic))
                for agent, who, at, status, ms, traffic in self.requests
                if agent == _bound(params, "selected_agent")
                and (principal is None or who == principal)
            )
        if columns == ["finished_at", "outcome"]:
            return Result(Row(one) for one in self.attempts)
        if columns == ["count"]:
            sql = str(statement.compile())
            self.counted.append(sql)
            if "FALSE" in sql:
                return Result([0])
            key = (str(_bound(params, "source")), str(_bound(params, "entity")))
            return Result([self.kept.get(key, 0)])
        if columns == ["direction", "outcome", "recorded_at"]:
            return Result(Row(one) for one in self.deliveries)
        if columns == ["max"]:
            return Result([max(at for _, _, at in self.deliveries)])
        if columns == ["principal_id"]:
            principal = _bound(params, "principal_id")
            return Result(
                one for one in dict.fromkeys(self.bound) if principal is None or one == principal
            )
        return None


def _bound(params: Mapping[str, Any], prefix: str) -> Any:
    """The value bound under the first parameter named from this column, or None."""
    for key, value in params.items():
        if key == prefix or key.startswith(f"{prefix}_"):
            return value
    return None


def spend_row(principal: str, cost: int, at: datetime) -> SpendActualRow:
    return SpendActualRow(
        principal_id=principal,
        principal_kind="human",
        traffic=TrafficClass.HUMAN_INTERACTIVE.value,
        department="web",
        agent_id=AGENT,
        model="m",
        lane=Lane.ANSWER.value,
        cost_minor=cost,
        at=at,
        trace_id="t" * 32,
    )


class Sync:
    """`ConnectorSyncRecords` answering one newest attempt for xero."""

    async def states(self) -> Mapping[str, SyncState]:
        return {
            "xero": SyncState(
                connector="xero",
                finished_at=NOW - timedelta(hours=1),
                outcome=SyncOutcome.FAILED,
                health=HealthState.DEGRADED,
                consecutive_failures=2,
                next_attempt_at=NOW + timedelta(hours=1),
                detail="a sentence",
                last_synced_at=NOW - timedelta(days=1),
            )
        }


def library_skill(name: str, description: str, days_ago: int) -> LibrarySkill:
    one = imported(name)
    skill = one.skill.model_copy(update={"description": description})
    made = one.model_copy(update={"skill": skill})
    return LibrarySkill(
        imported=made,
        digest=skill.digest(),
        submitted_by="u_admin",
        submitted_at=NOW - timedelta(days=days_ago),
    )


class Library:
    """A `brain.skill_routes.SkillLibrary` holding two versions of one skill."""

    def __init__(self) -> None:
        self.skills = (
            library_skill("triage", "Use when triage comes up.", 2),
            library_skill("triage", "Use when a ticket needs triage.", 20),
        )

    async def library(self, limit: int = 500) -> tuple[LibrarySkill, ...]:
        return self.skills[:limit]

    async def skill(self, digest: str) -> LibrarySkill | None:
        return None

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        raise AssertionError("a stats read wrote")

    async def decide(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        raise AssertionError("a stats read wrote")

    async def assign(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a stats read wrote")

    async def categories(self, names: Sequence[str]) -> Mapping[str, tuple[str, ...]]:
        return {}

    async def categorise(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a stats read wrote")

    # The protocol's retirement and detachment half (`0139`). Without them this is no
    # `SkillLibrary`, and `library_of` quietly falls back to the database the stub cannot answer.
    async def retirements(self, digests: Sequence[str]) -> Mapping[str, Any]:
        return {}

    async def retire(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a stats read wrote")

    async def detach(self, *args: Any, **kwargs: Any) -> bool:
        raise AssertionError("a stats read wrote")

    async def assignment_history(self, names: Sequence[str]) -> tuple[tuple[Any, ...], ...]:
        return (), ()

    # The protocol's export half (`0191`), for the same reason as the half above.
    async def script_bytes(self, digest: str) -> dict[str, bytes]:
        return {}

    async def export(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a stats read wrote")

    async def rehearse(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a stats read wrote")

    async def rehearsals(self, digests: Sequence[str]) -> Mapping[str, tuple[Any, ...]]:
        return {}


@pytest.fixture
def held() -> Held:
    return Held()


@pytest.fixture
def served(held: Held) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(held.answer)
        state = client.app.state  # type: ignore[attr-defined]
        state.connector_records = Records((a_connection("xero"), a_connection("hubspot")))
        state.connector_sync_records = Sync()
        state.skill_library = Library()
        yield client, stub


def stats(client: TestClient, pid: str, module: str, name: str) -> Any:
    return get(client, pid, f"{API_PREFIX}/console/{module}/{name}/stats")


def assert_same_refusal(first: Any, second: Any) -> None:
    """Two refusals a reader cannot tell apart: one status, one sentence, one set of keys."""
    assert first.status_code == second.status_code == 404
    assert first.json()["message"] == second.json()["message"]
    assert set(first.json()) == set(second.json())


# ------------------------------------------------------------------------------ agents
def test_a_reader_of_everybodys_usage_is_counted_over_every_request_the_agent_answered(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case. Delete this and every narrowing below is satisfied by a page of
    noughts."""
    client, _ = served
    response = stats(client, "u_admin", "agents", AGENT)
    assert response.status_code == 200, response.text
    body = AgentStatsView.model_validate(response.json())

    week, month, *_ = body.periods
    assert (body.basis, week.range, month.range) == ("everyone", "7d", "30d")
    assert (week.runs, week.answered, week.nothing_returned) == (3, 2, 0)
    assert (month.runs, month.answered, month.nothing_returned) == (4, 2, 1)
    assert month.p50_latency_ms == 600.0
    assert body.last_active is not None
    assert body.at_least is False


def test_a_reader_without_the_usage_read_is_counted_over_their_own_requests_in_the_query(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """Delete this and an agent's page counts colleagues' requests for somebody who may not read
    usage, and the statement fetches their rows into this process to do it."""
    client, _ = served
    body = AgentStatsView.model_validate(stats(client, "u_narrow", "agents", AGENT).json())

    week, month, *_ = body.periods
    assert body.basis == "own"
    assert (week.runs, month.runs, month.nothing_returned) == (1, 2, 1)
    assert month.p50_latency_ms == 300.0
    asked = [one for one in held.params if "selected_agent_1" in one]
    assert asked and all(_bound(one, "principal") == "u_narrow" for one in asked)


def test_an_agent_outside_the_audience_is_the_404_an_agent_that_does_not_exist_gets(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """Delete this and the stats address lists the company's agents one guessed slug at a time."""
    client, _ = served
    hidden = stats(client, "u_narrow", "agents", HIDDEN_AGENT)
    missing = stats(client, "u_narrow", "agents", "no_such_agent")

    assert_same_refusal(hidden, missing)
    assert not [one for one in held.params if _bound(one, "selected_agent") == HIDDEN_AGENT]
    assert stats(client, "u_elsewhere", "agents", HIDDEN_AGENT).status_code == 200


def test_cost_is_not_recorded_rather_than_nought_until_a_run_writes_one(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and an agent that cost money shows 0 while nothing records a run's cost, and
    once something does the figure has to follow the budget screen's basis. Both halves set the
    flag, because the usage recorder turned it on and the unrecorded half must still be tested."""
    client, _ = served
    monkeypatch.setattr(console_stats_routes, "RUN_SPEND_IS_RECORDED", False)
    unrecorded = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    assert [one.cost_minor for one in unrecorded.periods] == [None] * 4
    assert [one.callers for one in unrecorded.periods] == [[]] * 4
    assert [one.figure for one in unrecorded.unrecorded] == ["model_cost"]

    monkeypatch.setattr(console_stats_routes, "RUN_SPEND_IS_RECORDED", True)
    everyone = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    own = AgentStatsView.model_validate(stats(client, "u_narrow", "agents", AGENT).json())

    assert [one.cost_minor for one in everyone.periods[:3]] == [120, 420, 500]
    assert everyone.cost_basis == "everyone"
    assert [one.cost_minor for one in own.periods[:3]] == [120, 120, 120]
    assert own.cost_basis == "own"
    assert everyone.unrecorded == []


def _month_start() -> datetime:
    return NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def test_an_agents_figures_are_given_over_seven_thirty_and_ninety_days_and_the_month_to_date(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.1.3.2: the page's range selector offers four windows, so the route must send four.
    The sixty-day request is in ninety days and in no shorter window, and the month to date holds
    exactly the requests since the first of this month, whatever today's date is. Delete this and
    the selector can offer a window the route never counted."""
    client, _ = served
    body = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())

    assert [one.range for one in body.periods] == ["7d", "30d", "90d", "mtd"]
    week, month, quarter, to_date = body.periods
    assert (week.runs, month.runs, quarter.runs) == (3, 4, 5)
    assert to_date.since == _month_start()
    since_first = sum(
        1 for agent, _, at, *_ in Held().requests if agent == AGENT and at >= _month_start()
    )
    assert to_date.runs == since_first


def test_an_agents_messages_are_the_runs_a_person_sent_and_never_an_automations(
    served: tuple[TestClient, Stub],
) -> None:
    """M39.1.3.1: spend, runs and messages are the agent's headline figures. A message is a run a
    person started; the automation's run is a run and not a message. Delete this and the message
    figure can be the run figure under another name."""
    client, _ = served
    body = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())

    week, month, quarter, _ = body.periods
    assert (week.runs, week.messages) == (3, 2)
    assert (month.runs, month.messages) == (4, 3)
    assert (quarter.runs, quarter.messages) == (5, 4)


def test_the_cost_per_person_is_heaviest_first_and_only_the_readers_own_on_the_narrower_basis(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M39.1.3.3: cost attributed per caller, so one heavy user is visible to a reader of
    everybody's spend, named from the directory. A reader without the budget read is shown their
    own row and nobody else's, and never a remainder. Delete this and the list can name
    colleagues to anybody who opens the agent."""
    client, _ = served
    monkeypatch.setattr(console_stats_routes, "RUN_SPEND_IS_RECORDED", True)
    everyone = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    own = AgentStatsView.model_validate(stats(client, "u_narrow", "agents", AGENT).json())

    month = everyone.periods[1]
    assert [(one.principal_id, one.name, one.spend_minor) for one in month.callers] == [
        ("u_admin", "Admin Person", 300),
        ("u_narrow", "Narrow Person", 120),
    ]
    assert [one.spend_minor for one in everyone.periods[2].callers] == [380, 120]
    assert [
        [(one.principal_id, one.spend_minor) for one in period.callers]
        for period in own.periods[:3]
    ] == [[("u_narrow", 120)]] * 3


def _monthly_budget(ceiling: int) -> BudgetVersionRow:
    return BudgetVersionRow(
        level="agent",
        subject=AGENT,
        period="month",
        ceiling_minor=ceiling,
        version=1,
        author="u_admin",
        effective_from=NOW - timedelta(days=400),
        reason="set on the agent's page",
        alert_fractions=[],
    )


def test_the_projection_is_against_the_agents_own_monthly_budget_for_a_reader_of_everybodys_spend(
    served: tuple[TestClient, Stub], held: Held, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M39.1.3.4: the month-end projection is everybody's month to date against the agent's own
    monthly budget. Absent with no budget set, and withheld from a reader of their own spend,
    because a projection of one person's spend against a ceiling everybody shares is a confident
    figure that is wrong. Delete this and the page can project nothing, or project somebody's
    afternoon."""
    client, _ = served
    monkeypatch.setattr(console_stats_routes, "RUN_SPEND_IS_RECORDED", True)
    assert (
        AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json()).projection
        is None
    )

    held.budgets.append(_monthly_budget(1))
    shown = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    withheld = AgentStatsView.model_validate(stats(client, "u_narrow", "agents", AGENT).json())

    to_date = sum(one.cost_minor for one in held.spend if one.at >= _month_start())
    assert shown.projection is not None
    assert (shown.projection.spent_minor, shown.projection.ceiling_minor) == (to_date, 1)
    assert shown.projection.projected_minor >= to_date
    assert shown.projection.over_ceiling is (shown.projection.projected_minor > 1)
    assert withheld.projection is None


# ------------------------------------------------------------------------------ skills
def test_a_reader_of_the_library_sees_a_skills_versions_arrivals_and_runs(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for skills: a reader of everybody's usage is counted over every run of
    the skill by an agent they may see, and nothing is listed as unrecorded. Delete this and the
    runs figure can be nought for everybody with every narrowing test below still green."""
    client, _ = served
    response = stats(client, "u_admin", "skills", "triage")
    assert response.status_code == 200, response.text
    body = SkillStatsView.model_validate(response.json())

    assert (body.agents_pinned, body.pinned_versions, body.versions) == (0, 0, 2)
    assert [one.versions_added for one in body.periods] == [1, 2]
    assert body.run_basis == "everyone"
    assert [one.runs for one in body.periods] == [2, 3]
    assert body.last_used is not None
    assert abs(body.last_used - (NOW - timedelta(days=1))) < timedelta(seconds=1)
    assert body.at_least is False
    assert body.unrecorded == []


def test_a_skills_runs_exclude_agents_the_reader_may_not_see_in_the_query(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """The finance agent ran the skill two hours ago, and `u_admin` may not see that agent. Delete
    this and a skill's page counts, and dates, runs by an agent the reader may not be told exists,
    and the statement fetches them into this process to do it."""
    client, _ = served
    body = SkillStatsView.model_validate(stats(client, "u_admin", "skills", "triage").json())

    assert [one.runs for one in body.periods] == [2, 3]
    assert body.last_used is not None and body.last_used < NOW - timedelta(hours=12)
    asked = held.asked_uses
    assert asked and all(_bound(one, "agent_id") == [AGENT] for one in asked)


def test_a_skills_runs_are_the_readers_own_when_they_may_not_read_usage_in_the_query(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """`u_wide` reads the library and not usage. Delete this and a skill's page tells somebody
    who may not read colleagues' usage how often colleagues ran it."""
    client, _ = served
    body = SkillStatsView.model_validate(stats(client, "u_wide", "skills", "triage").json())

    assert body.run_basis == "own"
    assert [one.runs for one in body.periods] == [1, 1]
    assert body.last_used is not None
    assert abs(body.last_used - (NOW - timedelta(days=3))) < timedelta(seconds=1)
    assert held.asked_uses
    assert all(_bound(one, "principal_id") == "u_wide" for one in held.asked_uses)


@pytest.mark.parametrize("pid", ["u_narrow", "u_none"])
def test_a_skill_the_reader_may_not_be_told_of_is_the_404_a_missing_skill_gets(
    served: tuple[TestClient, Stub], pid: str
) -> None:
    """`u_narrow` holds the Skills screen in one department, which lists no library row and no
    agent of theirs runs it; `u_none` holds nothing. Delete this and the address says which
    skills the library holds."""
    client, _ = served

    assert_same_refusal(
        stats(client, pid, "skills", "triage"), stats(client, "u_admin", "skills", "no_such_skill")
    )


@pytest.mark.parametrize("pid", ["u_narrow", "u_none"])
def test_a_skill_out_of_reach_reads_no_run_of_it(
    served: tuple[TestClient, Stub], held: Held, pid: str
) -> None:
    """Delete this and a refused skill still costs a query over its runs, whose timing is the
    difference the one 404 is there to remove."""
    client, _ = served

    assert stats(client, pid, "skills", "triage").status_code == 404
    assert held.asked_uses == []


# -------------------------------------------------------------------------- connectors
def test_a_reader_of_a_connector_sees_its_health_attempts_and_the_ids_their_scope_admits(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """The positive case, and the index narrowing: `u_admin` reads invoices and not contacts, so
    the five invoice ids are counted and the two contacts are not, with `FALSE` in the statement
    for contacts rather than a missing clause."""
    client, _ = served
    response = stats(client, "u_admin", "connectors", "xero")
    assert response.status_code == 200, response.text
    body = ConnectorStatsView.model_validate(response.json())

    assert (body.health, body.consecutive_failures, body.index_ids) == ("degraded", 2, 5)
    assert body.last_read_to_the_end is not None
    week, month = body.periods
    assert (week.attempts, week.read_to_the_end, week.failures, week.quota_waits) == (2, 1, 1, 0)
    assert (month.attempts, month.quota_waits) == (3, 1)
    assert body.unrecorded == []
    contact = [sql for sql in held.counted if "FALSE" in sql]
    assert len(contact) == 1


def test_a_reader_of_everybodys_usage_is_counted_over_every_live_read_of_the_source(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for live reads: three questions read xero, one of them nine days ago,
    and hubspot's read is another source's. Delete this and a live-read count of nought for
    everybody passes every narrowing test below."""
    client, _ = served
    body = ConnectorStatsView.model_validate(stats(client, "u_admin", "connectors", "xero").json())

    assert body.live_read_basis == "everyone"
    assert [one.live_reads for one in body.periods] == [2, 3]
    assert body.last_live_read is not None
    assert abs(body.last_live_read - (NOW - timedelta(days=1))) < timedelta(seconds=1)


def test_a_reader_without_the_usage_read_is_counted_over_their_own_live_reads_in_the_query(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """`u_wide` reads every connector and not usage. Delete this and a source's page tells
    them how often colleagues' questions read it, and the statement fetches those rows to say so."""
    client, _ = served
    body = ConnectorStatsView.model_validate(stats(client, "u_wide", "connectors", "xero").json())

    assert body.live_read_basis == "own"
    assert [one.live_reads for one in body.periods] == [1, 1]
    assert body.last_live_read is not None
    assert abs(body.last_live_read - (NOW - timedelta(days=2))) < timedelta(seconds=1)
    assert held.asked_reads
    assert all(_bound(one, "principal") == "u_wide" for one in held.asked_reads)


def test_the_source_s_calls_are_told_to_a_reader_of_everybody_s_usage_and_to_nobody_else(
    served: tuple[TestClient, Stub],
) -> None:
    """M11.3.4 on the route: a process with no live reader says so to `u_admin`, one with a reader
    tells `u_admin` its count from nought, and `u_wide`, who reads only their own usage, is told
    why there are none rather than handed everybody's calls either way. Each case is set on the
    state rather than left to the lifespan, which builds a reader where this run has a database
    (`brain.app`, since the figure tools of M11.7.1 share it). Delete this and the route can serve
    the calls every question made to a reader who may not see anybody else's questions, or serve
    nought where nothing counts."""
    from brain.console_stats_routes import (
        CALLS_ARE_EVERYBODY_S,
        CALLS_ARE_THIS_PROCESS_S,
        NO_LIVE_READER_HERE,
    )
    from brain.ops.live_read_run import live_records_for

    client, _ = served
    state = client.app.state  # type: ignore[attr-defined]

    state.live_records = None
    wide = ConnectorStatsView.model_validate(stats(client, "u_admin", "connectors", "xero").json())
    own = ConnectorStatsView.model_validate(stats(client, "u_wide", "connectors", "xero").json())
    assert (wide.calls, wide.calls_told) == (None, NO_LIVE_READER_HERE)
    assert (own.calls, own.calls_told) == (None, CALLS_ARE_EVERYBODY_S)

    state.live_records = live_records_for(state.db_sessions, None)
    wide = ConnectorStatsView.model_validate(stats(client, "u_admin", "connectors", "xero").json())
    own = ConnectorStatsView.model_validate(stats(client, "u_wide", "connectors", "xero").json())
    assert wide.calls is not None and (wide.calls.requests, wide.calls.quiet) == (0, True)
    assert wide.calls_told == CALLS_ARE_THIS_PROCESS_S
    assert (own.calls, own.calls_told) == (None, CALLS_ARE_EVERYBODY_S)


def test_a_connector_outside_the_readers_grant_is_the_404_an_unconnected_source_gets(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """`u_narrow` may read hubspot only. Delete this and naming a source is a disclosure the
    Connectors screen's whole list is filtered to prevent."""
    client, _ = served
    hidden = stats(client, "u_narrow", "connectors", "xero")
    missing = stats(client, "u_narrow", "connectors", "freshdesk")

    assert_same_refusal(hidden, missing)
    assert_same_refusal(stats(client, "u_none", "connectors", "xero"), missing)
    assert held.counted == []
    assert held.asked_reads == []
    mine = ConnectorStatsView.model_validate(
        stats(client, "u_narrow", "connectors", "hubspot").json()
    )
    assert (mine.connector, mine.index_ids, mine.health) == ("hubspot", 0, None)


# ---------------------------------------------------------------------------- channels
def test_a_channels_manager_who_reads_people_sees_its_traffic_and_everybody_bound(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for channels, and that answers are named as told apart by nothing."""
    client, _ = served
    response = stats(client, "u_admin", "channels", "lark")
    assert response.status_code == 200, response.text
    body = ChannelStatsView.model_validate(response.json())

    week, month = body.periods
    assert (week.received, week.sent, week.failed) == (1, 1, 0)
    assert month.failed == 1
    assert (body.bound_people, body.bound_basis) == (3, "everyone")
    assert body.last_event is not None
    assert [one.figure for one in body.unrecorded] == ["answered"]


def test_a_manager_who_may_not_read_people_is_told_only_whether_they_are_bound(
    served: tuple[TestClient, Stub], held: Held
) -> None:
    """Delete this and a channel manager with no People read is handed a census of who uses the
    channel, and the statement fetches every binding to count it."""
    client, _ = served
    held.params.clear()
    body = ChannelStatsView.model_validate(stats(client, "u_narrow", "channels", "webhook").json())

    assert (body.bound_people, body.bound_basis) == (1, "own")
    assert any(_bound(one, "principal_id") == "u_narrow" for one in held.params)


@pytest.mark.parametrize("pid", ["u_narrow", "u_none"])
def test_a_channel_the_reader_may_not_manage_is_the_404_a_name_that_is_no_channel_gets(
    served: tuple[TestClient, Stub], pid: str
) -> None:
    """Delete this and the stats address says which channels an install runs."""
    client, _ = served

    assert_same_refusal(
        stats(client, pid, "channels", "lark"), stats(client, "u_admin", "channels", "pigeon")
    )


# ----------------------------------------------------------------------- the shapes
def test_no_view_carries_a_field_named_like_a_count_of_what_was_withheld() -> None:
    """Delete this and a `total` beside a narrowed count is one edit away and nothing says no."""
    views: list[type[BaseModel]] = [
        getattr(console_stats_routes, name)
        for name in dir(console_stats_routes)
        if name.endswith("View") and isinstance(getattr(console_stats_routes, name), type)
    ]

    assert len(views) >= 8
    assert [
        f"{one.__name__}.{field}"
        for one in views
        for field in one.model_fields
        if field in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
    ] == []


def test_the_statements_bound_what_they_read_and_narrow_before_the_bound() -> None:
    """Delete this and a narrower reader's request list is cut before it is narrowed, so a full
    page says there were other people's requests."""
    own = agent_requests(AGENT, NOW, basis=Basis.OWN, caller_id="u_narrow")
    everyone = agent_requests(AGENT, NOW, basis=Basis.EVERYONE, caller_id="u_narrow")

    assert "principal" in str(own.whereclause)
    assert "principal" not in str(everyone.whereclause)
    for statement in (
        own,
        connector_attempts("xero", NOW),
        channel_deliveries(Channel.LARK, NOW),
    ):
        assert statement.compile().params["param_1"] == MAX_ACTIVITY_ROWS
    assert "principal_id" in str(
        channel_bindings(Channel.LARK, basis=Basis.OWN, caller_id="u_narrow").whereclause
    )
    nothing = EntitlementSet(principal_id="u_none", grants=())
    assert "FALSE" in str(index_ids("xero", "xero_invoice", nothing, NOW).compile())

    reads_own = connector_live_reads("xero", NOW, basis=Basis.OWN, caller_id="u_narrow")
    reads_all = connector_live_reads("xero", NOW, basis=Basis.EVERYONE, caller_id="u_narrow")
    uses_own = skill_invocations("triage", [AGENT], NOW, basis=Basis.OWN, caller_id="u_narrow")
    uses_all = skill_invocations("triage", [AGENT], NOW, basis=Basis.EVERYONE, caller_id="u")
    assert "principal" in str(reads_own.whereclause)
    assert "principal" not in str(reads_all.whereclause)
    assert "principal_id" in str(uses_own.whereclause)
    assert "principal_id" not in str(uses_all.whereclause)
    assert "agent_id IN" in str(uses_all.whereclause)
    assert reads_own.compile().params["param_1"] == MAX_ACTIVITY_ROWS
    assert uses_own.compile().params["param_1"] == MAX_ACTIVITY_ROWS


# ---------------------------------------------------------------------- the database
DB_TABLES = (
    "obs.request_telemetry",
    "agent.skill_invocation",
    "ops.connector_connection",
    "ops.connector_sync",
    "proj.record",
    "ops.channel_delivery",
    "auth.principal",
    "auth.principal_identity",
)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """The tables these statements read, built from the models, with the ledger's default
    partition, in a database of this file's own."""
    from tests.fixtures.scratch_postgres import modelled, sql

    with modelled("brain_test_console_stats_routes", DB_TABLES) as url:
        sql(
            url,
            "CREATE TABLE obs.request_telemetry_default PARTITION OF obs.request_telemetry DEFAULT",
        )
        yield url


def _rows(url: str, statement: Any) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import engine, run

    async def go() -> list[tuple[Any, ...]]:
        built = engine(url)
        try:
            async with built.connect() as conn:
                return [tuple(one) for one in (await conn.execute(statement)).all()]
        finally:
            await built.dispose()

    return run(go)


def test_the_request_statement_returns_only_the_readers_rows_on_the_narrower_basis(
    database: str,
) -> None:
    """Run on PostgreSQL. Delete this and the principal predicate is proved against a stub that
    reads it, and never against the server that has to apply it."""
    from tests.fixtures.scratch_postgres import sql

    for who, days in (("u_narrow", 1), ("u_admin", 2), ("u_narrow", 40)):
        sql(
            database,
            "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal, "
            "entitlement_hash, lane, cache_hit, status, duration_ms, selected_agent) VALUES "
            "(%s, 't1', 'human_interactive', %s, %s, 'answer', false, 'answered', 10, %s)",
            NOW - timedelta(days=days),
            who,
            "a" * 32,
            AGENT,
        )
    since = NOW - timedelta(days=30)

    own = _rows(database, agent_requests(AGENT, since, basis=Basis.OWN, caller_id="u_narrow"))
    everyone = _rows(
        database, agent_requests(AGENT, since, basis=Basis.EVERYONE, caller_id="u_narrow")
    )

    assert [one[0] for one in own] == ["u_narrow"]
    assert sorted(one[0] for one in everyone) == ["u_admin", "u_narrow"]
    assert [one[2] for one in own] == [RequestStatus.ANSWERED.value]


def test_the_index_count_admits_only_ids_the_readers_row_scope_admits(database: str) -> None:
    """Run on PostgreSQL. Delete this and the kept-ids figure is proved over a stub, and a scope
    compiled wrongly counts every invoice for a reader who may read one tenant's."""
    from tests.fixtures.scratch_postgres import sql

    for source_id, tenant in (("i1", "t_a"), ("i2", "t_a"), ("i3", "t_b")):
        sql(
            database,
            "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at) "
            "VALUES ('xero', 'xero_invoice', %s, %s::jsonb, now())",
            source_id,
            f'{{"tenant_id": "{tenant}"}}',
        )
    one_tenant = EntitlementSet(
        principal_id="u_narrow",
        grants=(
            Grant(capability=Capability(value="read:xero_invoice"), scope=only("tenant_id", "t_a")),
        ),
    )
    every_tenant = EntitlementSet(
        principal_id="u_admin",
        grants=(Grant(capability=Capability(value="read:xero_invoice"), scope=EVERYWHERE),),
    )
    nothing = EntitlementSet(principal_id="u_none", grants=())

    assert _rows(database, index_ids("xero", "xero_invoice", one_tenant, NOW)) == [(2,)]
    assert _rows(database, index_ids("xero", "xero_invoice", every_tenant, NOW)) == [(3,)]
    assert _rows(database, index_ids("xero", "xero_invoice", nothing, NOW)) == [(0,)]


def test_the_channel_and_connector_statements_run_and_narrow_bindings_to_the_caller(
    database: str,
) -> None:
    """Run on PostgreSQL. Delete this and the channel's and connector's statements are only ever
    compiled, and a live-connection join or a binding predicate the server rejects ships."""
    from tests.fixtures.scratch_postgres import sql

    connection = uuid.uuid4()
    sql(
        database,
        "INSERT INTO ops.connector_connection (id, connector, settings, digest, connected_by) "
        "VALUES (%s, 'xero', '{}'::jsonb, %s, 'u_admin')",
        connection,
        "d" * 64,
    )
    sql(
        database,
        "INSERT INTO ops.connector_sync (connection_id, connector, started_at, finished_at, "
        "outcome, health, next_attempt_at, detail) VALUES (%s, 'xero', %s, %s, 'synced', 'ok', "
        "%s, 'read')",
        connection,
        NOW - timedelta(days=1),
        NOW - timedelta(days=1),
        NOW,
    )
    sql(
        database,
        "INSERT INTO ops.channel_delivery (channel, direction, outcome) "
        "VALUES ('lark', 'inbound', 'accepted')",
    )
    for pid in ("u_narrow", "u_admin"):
        sql(
            database,
            "INSERT INTO auth.principal (id, kind, employment, display_name) "
            "VALUES (%s, 'human', 'staff', %s)",
            pid,
            pid,
        )
        sql(
            database,
            "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at) "
            "VALUES ('lark', %s, %s, now())",
            {"u_narrow": "a", "u_admin": "b"}[pid] * 64,
            pid,
        )
    since = NOW - timedelta(days=30)

    assert [one[1] for one in _rows(database, connector_attempts("xero", since))] == ["synced"]
    assert len(_rows(database, channel_deliveries(Channel.LARK, since))) == 1
    own = _rows(database, channel_bindings(Channel.LARK, basis=Basis.OWN, caller_id="u_narrow"))
    everyone = _rows(
        database, channel_bindings(Channel.LARK, basis=Basis.EVERYONE, caller_id="u_narrow")
    )
    assert own == [("u_narrow",)]
    assert sorted(everyone) == [("u_admin",), ("u_narrow",)]


def test_a_test_of_the_connection_is_not_counted_as_an_attempt_to_read_it(database: str) -> None:
    """Run on PostgreSQL. A `probed` row (`0142`) is a test a person asked for, and the statement
    the figures are read from leaves it out beside the read it follows. Delete this and every press
    of Test connection is counted as an attempt, and a failed test as a failed read, on the source's
    Dashboard (M27.15.8)."""
    from tests.fixtures.scratch_postgres import sql

    connection = uuid.uuid4()
    sql(
        database,
        "INSERT INTO ops.connector_connection (id, connector, settings, digest, connected_by) "
        "VALUES (%s, 'hubspot', '{}'::jsonb, %s, 'u_admin')",
        connection,
        "e" * 64,
    )
    for outcome, health, days in (("synced", "ok", 2), ("probed", "down", 1)):
        sql(
            database,
            "INSERT INTO ops.connector_sync (connection_id, connector, started_at, finished_at, "
            "outcome, health, next_attempt_at, detail) VALUES (%s, 'hubspot', %s, %s, %s, %s, "
            "%s, 'said')",
            connection,
            NOW - timedelta(days=days),
            NOW - timedelta(days=days),
            outcome,
            health,
            NOW,
        )

    found = _rows(database, connector_attempts("hubspot", NOW - timedelta(days=30)))

    assert [one[1] for one in found] == ["synced"]


def test_the_live_read_statement_returns_this_sources_rows_and_the_readers_when_narrower(
    database: str,
) -> None:
    """Run on PostgreSQL. Delete this and the live-read predicates, the source and the person, are
    proved against a stub that reads them, and never against the server that has to apply them."""
    from tests.fixtures.scratch_postgres import sql

    for who, source, days in (
        ("u_narrow", "hubspot", 1),
        ("u_admin", "hubspot", 2),
        ("u_narrow", "freshdesk", 1),
        ("u_narrow", "hubspot", 40),
    ):
        sql(
            database,
            "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal, "
            "entitlement_hash, lane, cache_hit, status, duration_ms, connector) VALUES "
            "(%s, 't2', 'human_interactive', %s, %s, 'answer', false, 'answered', 10, %s)",
            NOW - timedelta(days=days),
            who,
            "a" * 32,
            source,
        )
    since = NOW - timedelta(days=30)

    own = _rows(
        database, connector_live_reads("hubspot", since, basis=Basis.OWN, caller_id="u_narrow")
    )
    everyone = _rows(
        database,
        connector_live_reads("hubspot", since, basis=Basis.EVERYONE, caller_id="u_narrow"),
    )

    assert [one[0] for one in own] == ["u_narrow"]
    assert sorted(one[0] for one in everyone) == ["u_admin", "u_narrow"]


def test_the_skill_run_statement_returns_visible_agents_rows_and_the_readers_when_narrower(
    database: str,
) -> None:
    """Run on PostgreSQL. Delete this and the agent list and the person are proved against a stub,
    and an `IN` the server reads differently, or an empty list it refuses, ships."""
    from tests.fixtures.scratch_postgres import sql

    for trace, agent, who, skill, days in (
        ("s1", AGENT, "u_narrow", "triage", 1),
        ("s2", AGENT, "u_admin", "triage", 2),
        ("s3", HIDDEN_AGENT, "u_narrow", "triage", 1),
        ("s4", AGENT, "u_narrow", "other", 1),
        ("s5", AGENT, "u_narrow", "triage", 40),
    ):
        sql(
            database,
            "INSERT INTO agent.skill_invocation (trace_id, principal_id, agent_id, skill_name, "
            "digest, used_at) VALUES (%s, %s, %s, %s, %s, %s)",
            trace,
            who,
            agent,
            skill,
            "d" * 64,
            NOW - timedelta(days=days),
        )
    since = NOW - timedelta(days=30)

    def asked(agents: list[str], basis: Basis) -> list[tuple[Any, ...]]:
        return _rows(
            database, skill_invocations("triage", agents, since, basis=basis, caller_id="u_narrow")
        )

    assert [(one[0], one[1]) for one in asked([AGENT], Basis.OWN)] == [("u_narrow", AGENT)]
    assert sorted(one[0] for one in asked([AGENT], Basis.EVERYONE)) == ["u_admin", "u_narrow"]
    assert len(asked([AGENT, HIDDEN_AGENT], Basis.OWN)) == 2
    assert asked([], Basis.EVERYONE) == []
