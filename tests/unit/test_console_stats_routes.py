"""One entity's figures over HTTP: who is answered, who gets the 404 a missing name gets, and that
the figures a reader is given are over rows they may read.

Driven through the real application with signed-in people and a stub where the pool is. The stub
answers each statement by the columns it selects and **evaluates the reader's predicate from the
statement's own bound parameters** (the principal on the narrower basis, `FALSE` for an entity the
reader holds no read of), so a route that stopped composing the predicate would be caught here and
not agreed with. The database tests at the bottom run the same statements against PostgreSQL.

Every refusal is compared status to status and message to message with the answer a name that
matches nothing gets, and every refusal has a sibling proving the reader in reach is answered.

Task ids: M27.15.27, M27.15.33
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
    index_ids,
    router,
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
#: which is who a finance department's agent is visible to.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        *PLANES,
        *(
            Grant(capability=read(key), scope=EVERYWHERE)
            for key in ("usage", "budget", "skills", "connectors", "people")
        ),
        Grant(capability=INSTALL_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=Capability(value="read:invoice"), scope=EVERYWHERE),
    ),
    "u_narrow": (
        *PLANES,
        Grant(capability=read("skills"), scope=only("department", "web")),
        Grant(capability=read("connectors"), scope=only("connector", "hubspot")),
        Grant(capability=INSTALL_AUTHORITY, scope=only("connector", "webhook_channel")),
    ),
    "u_none": (),
    "u_elsewhere": PLANES,
}

NOW = datetime.now(UTC)
AGENT = "desk"
HIDDEN_AGENT = "finance_desk"


class Held:
    """What the stub database holds, answered by the columns a statement selects."""

    def __init__(self) -> None:
        self.agents: dict[str, AgentRow] = {
            AGENT: agent_row(AGENT),
            HIDDEN_AGENT: agent_row(
                HIDDEN_AGENT, level=Visibility.DEPARTMENT, department="finance"
            ),
        }
        #: (selected agent, principal, received, status, duration)
        self.requests: list[tuple[str, str, datetime, str, float]] = [
            (AGENT, "u_narrow", NOW - timedelta(days=1), "answered", 200.0),
            (AGENT, "u_narrow", NOW - timedelta(days=10), "nothing_returned", 400.0),
            (AGENT, "u_admin", NOW - timedelta(days=2), "answered", 800.0),
            (AGENT, "u_elsewhere", NOW - timedelta(days=3), "failed", 1600.0),
            (HIDDEN_AGENT, "u_elsewhere", NOW - timedelta(days=1), "answered", 50.0),
        ]
        self.spend: list[SpendActualRow] = [
            spend_row("u_narrow", 120, NOW - timedelta(days=1)),
            spend_row("u_admin", 300, NOW - timedelta(days=12)),
        ]
        self.attempts: list[tuple[datetime, str]] = [
            (NOW - timedelta(days=1), "synced"),
            (NOW - timedelta(days=2), "failed"),
            (NOW - timedelta(days=20), "quota"),
        ]
        #: Kept ids per (source, entity), which a count admits only when the scope is not FALSE.
        self.kept: dict[tuple[str, str], int] = {("xero", "invoice"): 5, ("xero", "contact"): 2}
        self.deliveries: list[tuple[str, str, datetime]] = [
            ("inbound", "accepted", NOW - timedelta(days=1)),
            ("outbound", "sent", NOW - timedelta(days=1)),
            ("outbound", "refused", NOW - timedelta(days=8)),
        ]
        self.bound: list[str] = ["u_narrow", "u_admin", "u_elsewhere"]
        self.params: list[dict[str, Any]] = []
        self.counted: list[str] = []

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
        if len(described) == 2 and columns[0] != "finished_at" and columns[0] != "direction":
            # The installs of the reader's agents. None is installed in these tests.
            return Result([])
        if described[0].get("entity") is SpendActualRow:
            return Result(self.spend)
        if columns == ["principal", "received_at", "status", "duration_ms"]:
            principal = _bound(params, "principal")
            return Result(
                Row((who, at, status, ms))
                for agent, who, at, status, ms in self.requests
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

    week, month = body.periods
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

    week, month = body.periods
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
    once something does the figure has to follow the budget screen's basis."""
    client, _ = served
    unrecorded = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    assert [one.cost_minor for one in unrecorded.periods] == [None, None]
    assert [one.figure for one in unrecorded.unrecorded] == ["model_cost"]

    monkeypatch.setattr(console_stats_routes, "RUN_SPEND_IS_RECORDED", True)
    everyone = AgentStatsView.model_validate(stats(client, "u_admin", "agents", AGENT).json())
    own = AgentStatsView.model_validate(stats(client, "u_narrow", "agents", AGENT).json())

    assert [one.cost_minor for one in everyone.periods] == [120, 420]
    assert everyone.cost_basis == "everyone"
    assert [one.cost_minor for one in own.periods] == [120, 120]
    assert own.cost_basis == "own"
    assert everyone.unrecorded == []


# ------------------------------------------------------------------------------ skills
def test_a_reader_of_the_library_sees_a_skills_versions_and_arrivals(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for skills, and that invocations are named as not recorded."""
    client, _ = served
    response = stats(client, "u_admin", "skills", "triage")
    assert response.status_code == 200, response.text
    body = SkillStatsView.model_validate(response.json())

    assert (body.agents_pinned, body.pinned_versions, body.versions) == (0, 0, 2)
    assert [one.versions_added for one in body.periods] == [1, 2]
    assert {one.figure for one in body.unrecorded} == {"runs_that_used_it", "last_used"}


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
    assert {one.figure for one in body.unrecorded} == {"live_reads", "last_live_read"}
    contact = [sql for sql in held.counted if "FALSE" in sql]
    assert len(contact) == 1


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
    assert "FALSE" in str(index_ids("xero", "invoice", nothing, NOW).compile())


# ---------------------------------------------------------------------- the database
DB_TABLES = (
    "obs.request_telemetry",
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
            "VALUES ('xero', 'invoice', %s, %s::jsonb, now())",
            source_id,
            f'{{"tenant_id": "{tenant}"}}',
        )
    one_tenant = EntitlementSet(
        principal_id="u_narrow",
        grants=(
            Grant(capability=Capability(value="read:invoice"), scope=only("tenant_id", "t_a")),
        ),
    )
    every_tenant = EntitlementSet(
        principal_id="u_admin",
        grants=(Grant(capability=Capability(value="read:invoice"), scope=EVERYWHERE),),
    )
    nothing = EntitlementSet(principal_id="u_none", grants=())

    assert _rows(database, index_ids("xero", "invoice", one_tenant, NOW)) == [(2,)]
    assert _rows(database, index_ids("xero", "invoice", every_tenant, NOW)) == [(3,)]
    assert _rows(database, index_ids("xero", "invoice", nothing, NOW)) == [(0,)]


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
