"""Live runs and models and health over HTTP: what each answers, refuses, and says it cannot.

Driven through the real application with the token machinery, the key source and the directory
borrowed from `tests/unit/test_api_routes.py` and `tests/unit/test_agent_routes.py`, for the
reason `tests/unit/test_skill_routes.py` gives about borrowing them. The stub session answers the
three statements these routes make and records every one, so a route that asked for something
else fails here rather than against a database nobody has.

**The two routes are refused differently and both shapes are asserted.** Live runs narrows row
by row and refuses nobody, so the property is that a reader holding nothing is answered exactly
what an install running nothing is answered. Models is whole-install and refuses anybody whose
basis is not everybody's, so the property is that every such reader gets one refusal and a
reader who may see everybody's is answered.

**The sentences each response carries about what it cannot show are held to the code that makes
them true**, by reading the source tree rather than trusting a constant: nothing writes a model
attempt, nothing stores a provider's health, the queue driver's tables get no policy, and nothing
calls a queue cancellation.

Task ids: M27.2.2, M27.2.3, M27.2.6
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain import operate_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import intersections_in
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.models.routing import Tier
from brain.operate_routes import (
    DEFAULT_WINDOW_HOURS,
    MAX_WINDOW_HOURS,
    MEASURES_THE_MODELS_SCREEN_DRAWS,
    TIER_HANDLES,
    LaneTrafficView,
    LiveRunsView,
    ModelsView,
    OwedControlView,
    ProviderView,
    RunningControlView,
    TierView,
    UnmeasuredView,
    fallbacks_between,
    lane_traffic,
    newest_run_of_each_control,
    requests_by_lane,
    running_from,
    unmeasured,
)
from brain.ops.controls import CONTROLS, control
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.queue import driver_rls_statements
from brain.ops.schedule_runner import STALLED_AFTER
from brain.ops.telemetry import FILLED_BY_A_MODEL_CALL, UNFILLABLE_TODAY
from tests.fixtures.http_client import Response
from tests.unit.test_agent_routes import Directory
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

RUNS = f"{API_PREFIX}/operate/runs"
MODELS = f"{API_PREFIX}/operate/models"

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: The source tree, for the claims a response makes about what the code does not do.
SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

RUN_READ = screen("runs").read.requires
QUEUE_READ = screen("queue").read.requires
MODEL_READ = screen("models").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)
EVERYWHERE = Scope.unrestricted()

#: What each person holds. `u_admin` holds all three screens and the configuration plane.
#: `u_narrow` holds live runs and not the queue, and `u_wide` the queue and not live runs, which
#: is the pair that shows one grant does not reach the other screen's rows. `u_prefix` holds all
#: three with only the existence plane, which a bare capability check would let in. `u_elsewhere`
#: holds all three scoped to one department, which no control and no whole-install figure has.
#: `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        Grant(capability=RUN_READ, scope=EVERYWHERE),
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=MODEL_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_narrow": (
        Grant(capability=RUN_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_wide": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_prefix": (
        Grant(capability=RUN_READ, scope=EVERYWHERE),
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=MODEL_READ, scope=EVERYWHERE),
        Grant(capability=EXISTENCE, scope=EVERYWHERE),
    ),
    "u_elsewhere": (
        Grant(capability=RUN_READ, scope=Scope.department("finance")),
        Grant(capability=QUEUE_READ, scope=Scope.department("finance")),
        Grant(capability=MODEL_READ, scope=Scope.department("finance")),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_none": (),
}


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ------------------------------------------------------------------- the stub session


class StubRow:
    """A result row answering both ways the routes read one: by attribute and as a tuple."""

    def __init__(self, **values: Any) -> None:
        self._values = values

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError as missing:
            raise AttributeError(name) from missing

    def _tuple(self) -> tuple[Any, ...]:
        return tuple(self._values.values())


class Stored:
    """What the stub database holds, and every statement it was asked."""

    def __init__(self) -> None:
        #: Each control's newest run: name, started, finished or None, report only.
        self.newest: list[tuple[str, datetime, datetime | None, bool]] = []
        #: Each control's last successful finish.
        self.successes: dict[str, datetime] = {}
        #: Requests finished per lane in whatever window was asked.
        self.lanes: list[tuple[str, int]] = []
        #: The ledger's sum of fallbacks in whatever window was asked, as the database returns it.
        self.fallbacks: int | None = 0
        self.statements: list[Any] = []


_STORED = Stored()


class StubResult:
    def __init__(self, rows: list[StubRow]) -> None:
        self._rows = rows

    def all(self) -> list[StubRow]:
        return list(self._rows)

    def scalar_one(self) -> Any:
        (row,) = self._rows
        return row._tuple()[0]


class StubSession(AsyncSession):
    """An `AsyncSession` answering the three statements these routes make, told apart by the
    names of the columns they select, and refusing any other."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STORED.statements.append(statement)
        columns = [one["name"] for one in statement.column_descriptions]
        if columns == ["name", "started_at", "finished_at", "report_only"]:
            return StubResult(
                [
                    StubRow(name=n, started_at=s, finished_at=f, report_only=r)
                    for n, s, f, r in _STORED.newest
                ]
            )
        if columns == ["name", "finished_at"]:
            return StubResult(
                [StubRow(name=n, finished_at=at) for n, at in _STORED.successes.items()]
            )
        if columns == ["lane", "count"]:
            return StubResult([StubRow(lane=lane, count=n) for lane, n in _STORED.lanes])
        if columns == ["fallbacks"]:
            return StubResult([StubRow(fallbacks=_STORED.fallbacks)])
        msg = f"the stub does not answer a statement selecting {columns}"
        raise AssertionError(msg)

    async def close(self) -> None:
        return None


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store per test, so one test's rows are never another's evidence."""
    global _STORED
    _STORED = Stored()
    yield _STORED


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def client(stored: Stored) -> Iterator[TestClient]:
    """The real application, its router registration included, with the stub where the pool is."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        yield c


def get(c: TestClient, pid: str, path: str) -> Response:
    response: Response = c.get(path, headers={"authorization": f"Bearer {token_for(pid)}"})
    return response


def ago(**delta: float) -> datetime:
    """An instant before the wall clock, because the route measures against the wall clock.

    Relative rather than fixed, which is the rule `token_for` states for the same reason: the
    route reads `datetime.now(UTC)`, so a fixed hour would be a stall or a lateness decided by
    the day the test ran rather than by the row.
    """
    return datetime.now(UTC) - timedelta(**delta)


def controls_in(items: list[dict[str, Any]]) -> list[str]:
    return [one["control"] for one in items]


def modules_using(symbol: str) -> list[str]:
    """Every module under `src/brain` whose code names `symbol`, as a posix path, in order.

    Read off the syntax tree rather than the text, because the modules that argue a symbol is
    unused name it in their docstrings, and a text search would count the argument as a use.
    """
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            named = (
                (isinstance(node, ast.Name) and node.id == symbol)
                or (isinstance(node, ast.Attribute) and node.attr == symbol)
                or (isinstance(node, ast.alias) and node.name == symbol)
            )
            if named:
                found.append(path.relative_to(SRC).as_posix())
                break
    return found


# --------------------------------------------------------------------- live runs


def test_a_reader_holding_the_runs_grant_is_shown_each_control_running_and_what_it_keeps_true(
    client: TestClient, stored: Stored
) -> None:
    """An unfinished newest run is listed with its start, its mode, and the registry's own
    sentence about what stops holding if it stops, oldest first.

    Delete this and the live runs screen can list nothing on an install whose worker is in the
    middle of a sweep, which is the screen reporting idle at the moment somebody asks."""
    stored.newest = [
        ("denial_digest", ago(minutes=2), None, False),
        ("retention_sweep", ago(minutes=5), None, True),
        ("canary_run", ago(hours=1), ago(minutes=50), False),
    ]

    body = get(client, "u_admin", RUNS).json()

    assert controls_in(body["running"]) == ["retention_sweep", "denial_digest"]
    sweep = body["running"][0]
    assert sweep["report_only"] is True
    assert sweep["keeps_true"] == control("retention_sweep").guards
    assert body["running"][1]["report_only"] is False


def test_a_run_older_than_the_schedulers_line_is_stalled_and_a_recent_one_is_not(
    client: TestClient, stored: Stored
) -> None:
    """`stalled` is the scheduler's own `STALLED_AFTER`, and the line is carried on the answer.

    Delete this and a run whose process died an hour ago reads exactly like one that started a
    minute ago, and the one question the screen can raise about it is never raised."""
    stored.newest = [
        ("denial_digest", ago(seconds=30), None, False),
        ("canary_run", ago(seconds=STALLED_AFTER.total_seconds() + 60), None, False),
    ]

    body = get(client, "u_admin", RUNS).json()

    stalled = {one["control"]: one["stalled"] for one in body["running"]}
    assert stalled == {"canary_run": True, "denial_digest": False}
    assert body["stalled_after_seconds"] == STALLED_AFTER.total_seconds()


def test_a_finished_newest_run_is_not_running_and_a_retired_control_is_not_either() -> None:
    """`running_from` keeps a row only when it has no finish and names a declared control.

    Delete this and a control whose newest run finished is listed as running, and a control
    removed from the registry keeps its last unfinished row on the screen for ever."""
    rows = [
        ("denial_digest", ago(minutes=1), None, False),
        ("canary_run", ago(minutes=9), ago(minutes=8), False),
        ("a_control_since_retired", ago(minutes=3), None, False),
    ]

    started, _ = running_from(rows, now=datetime.now(UTC))

    assert [name for name, _, _ in started] == ["denial_digest"]
    kept, _ = running_from(rows, now=datetime.now(UTC), controls=[control("canary_run")])
    assert kept == []


def test_the_statement_asks_for_each_controls_newest_run_and_not_its_newest_unfinished_one() -> (
    None
):
    """`DISTINCT ON` the name ordered by the start descending, with no filter on the finish.

    Delete this and the statement can filter unfinished rows first, after which a run that died
    at one and ran cleanly at two is listed as running now, for ever."""
    sql = str(newest_run_of_each_control().compile(dialect=DIALECT))

    assert "DISTINCT ON (ops.control_run.name)" in sql
    assert "ORDER BY ops.control_run.name, ops.control_run.started_at DESC" in sql
    assert "WHERE" not in sql


def test_a_control_is_waiting_from_its_last_attempt_and_late_from_its_last_success(
    client: TestClient, stored: Stored
) -> None:
    """A control tried a moment ago is not owed however long since it last worked; one last tried
    two days ago and last successful a month ago is owed and late by the month; one never run is
    owed on its first run and not late.

    Delete this and the route can hand `due_now` one map for both clocks. With the successes for
    both, a control failing on every tick is shown waiting while it runs; with the attempts for
    both, a control that has failed for a month is shown a day late."""
    long_ago = ago(days=30)
    stored.newest = [
        ("denial_digest", ago(seconds=5), ago(seconds=1), False),
        ("canary_run", ago(days=2), ago(days=2), False),
    ]
    stored.successes = {"denial_digest": long_ago, "canary_run": long_ago}

    body = get(client, "u_admin", RUNS).json()
    waiting = {one["control"]: one for one in body["waiting"]}

    assert "denial_digest" not in waiting
    assert waiting["canary_run"]["first_run"] is False
    assert waiting["canary_run"]["late_by_seconds"] > timedelta(days=25).total_seconds()
    assert waiting["canary_run"]["keeps_true"] == control("canary_run").guards
    assert waiting["restore_drill"]["first_run"] is True
    assert waiting["restore_drill"]["late_by_seconds"] == 0


def test_the_runs_grant_does_not_reach_the_waiting_list_nor_the_queue_grant_the_running_one(
    client: TestClient, stored: Stored
) -> None:
    """Each list is behind its own screen's grant, and holding one shows the other empty.

    Delete this and one grant governs both lists, so somebody given the queue is watching what
    runs and somebody given live runs reads the schedule, neither of which they were given."""
    stored.newest = [("denial_digest", ago(minutes=1), None, False)]

    runs_only = get(client, "u_narrow", RUNS).json()
    queue_only = get(client, "u_wide", RUNS).json()

    assert controls_in(runs_only["running"]) == ["denial_digest"]
    assert runs_only["waiting"] == []
    assert queue_only["running"] == []
    assert controls_in(queue_only["waiting"])


def test_a_reader_without_a_grant_is_answered_what_an_install_running_nothing_is_answered(
    client: TestClient, stored: Stored
) -> None:
    """Nothing held, only the existence plane, or a grant scoped to a department: each is a 200
    with two empty lists over a store holding a running control, and none of them is a refusal.

    Delete this and the lists can be filtered by a bare capability check, or a department grant
    can match a row that carries no department, and either shows the system's runs to a reader
    no administrator gave them to."""
    stored.newest = [("denial_digest", ago(minutes=1), None, False)]

    for pid in ("u_none", "u_prefix", "u_elsewhere"):
        response = get(client, pid, RUNS)
        assert response.status_code == 200
        assert response.json()["running"] == []
        assert response.json()["waiting"] == []

    assert controls_in(get(client, "u_admin", RUNS).json()["running"]) == ["denial_digest"]


def test_the_three_things_the_screen_cannot_show_are_said_on_every_answer(
    client: TestClient, stored: Stored
) -> None:
    """The in-flight requests, the queue driver's rows and a stop control are each a true flag,
    for a reader with every grant and for a reader with none.

    Delete this and the page loses the sentences that stop an empty table reading as an idle
    install, which is exactly the moment a person is waiting on an answer."""
    for pid in ("u_admin", "u_none"):
        body = get(client, pid, RUNS).json()
        assert body["requests_in_flight_are_not_recorded"] is True
        assert body["queue_is_not_readable"] is True
        assert body["no_run_can_be_stopped"] is True


def test_a_process_with_no_database_is_a_fault_and_not_an_idle_install(stored: Stored) -> None:
    """A reader on an instance with no pool gets the fault every route here gives.

    Delete this and a misconfigured instance answers that nothing is running, which an
    administrator reads as a fact about the worker."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        response = get(c, "u_admin", RUNS)

    assert response.status_code == 500
    assert isinstance(response.json().get("trace_id"), str)


# --------------------------------------------------------------- models and health


def test_a_reader_who_may_see_everybodys_figures_is_answered_and_every_other_reader_refused_alike(
    client: TestClient, stored: Stored
) -> None:
    """`u_admin` is answered; a reader holding nothing, one holding only the existence plane, one
    holding the grant for one department and one holding another screen's grant all get the one
    refusal, word for word.

    Delete this and a department-scoped reader is shown every department's traffic, which is the
    false figure `brain.console.operate.figure_basis` exists to withhold."""
    stored.lanes = [("fast", 3), ("answer", 7)]

    answered = get(client, "u_admin", MODELS)
    refused = [
        get(client, pid, MODELS) for pid in ("u_none", "u_prefix", "u_elsewhere", "u_narrow")
    ]

    assert answered.status_code == 200
    assert {one.status_code for one in refused} == {404}
    assert len({one.json()["message"] for one in refused}) == 1


def test_the_models_refusal_is_decided_before_the_database_is_reached_for(stored: Stored) -> None:
    """In the source, the refusal precedes the session; at run time, a refused reader on an
    instance with no pool is refused rather than told the process is broken.

    Delete this and the two lines can be swapped by somebody tidying, after which the deployment's
    state is readable by anybody who can reach the port."""
    tree = ast.parse(inspect.getsource(operate_routes.models).lstrip())
    refusal = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and "_models_not_answerable" in ast.unparse(node)
    )
    session = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node).startswith("_require_sessions")
    )
    assert refusal < session

    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        assert get(c, "u_none", MODELS).status_code == 404
        assert get(c, "u_admin", MODELS).status_code == 500


def test_every_lane_is_listed_in_its_declared_order_with_zero_for_a_quiet_one(
    client: TestClient, stored: Stored
) -> None:
    """The answer holds one row per `Lane`, the database's count where it gave one and zero
    where it did not, and a lane the ledger holds that `Lane` no longer declares is dropped.

    Delete this and a lane with no traffic disappears from the answer, so the share answered
    without a model is computed over whichever lanes happened to be busy."""
    stored.lanes = [("answer", 7), ("fast", 3), ("retired", 11)]

    lanes = get(client, "u_admin", MODELS).json()["lanes"]

    assert lanes == [
        {"lane": one.value, "requests": {"fast": 3, "answer": 7}.get(one.value, 0)} for one in Lane
    ]
    assert lane_traffic([]) == [LaneTrafficView(lane=one.value, requests=0) for one in Lane]


def test_the_window_is_the_hours_asked_for_and_ends_at_the_instant_admitted(
    client: TestClient, stored: Stored
) -> None:
    """`end - start` is the hours asked for, or seven days when nobody asks, and the statement
    counts over exactly that half-open window.

    Delete this and the figure beside "Last 7 days" can be over a window of any length."""
    asked = get(client, "u_admin", f"{MODELS}?hours=5").json()
    default = get(client, "u_admin", MODELS).json()

    def span(body: dict[str, Any]) -> timedelta:
        return datetime.fromisoformat(body["end"]) - datetime.fromisoformat(body["start"])

    assert span(asked) == timedelta(hours=5)
    assert span(default) == timedelta(hours=DEFAULT_WINDOW_HOURS) == timedelta(days=7)

    start, end = datetime(2019, 3, 1, tzinfo=UTC), datetime(2019, 3, 8, tzinfo=UTC)
    compiled = requests_by_lane(start, end).compile(dialect=DIALECT)
    sql = str(compiled)
    assert "count(*)" in sql
    assert "GROUP BY obs.request_telemetry.lane" in sql
    assert "obs.request_telemetry.received_at >=" in sql
    assert "obs.request_telemetry.received_at <" in sql
    assert sorted(compiled.params.values()) == [start, end]


def test_a_window_outside_the_bound_is_refused_and_the_bound_is_the_service_level_routes(
    client: TestClient,
) -> None:
    """Zero hours and one hour over the bound are both 422, and the bound both routes declare in
    the application's own document is the same number.

    Delete this and the page's two requests for one window can be bounded differently, so a
    window one of them answers is refused by the other on the same screen."""
    over = get(client, "u_admin", f"{MODELS}?hours={MAX_WINDOW_HOURS + 1}")
    under = get(client, "u_admin", f"{MODELS}?hours=0")
    assert over.status_code == under.status_code == 422

    document = client.app.openapi()  # type: ignore[attr-defined]

    def bound(path: str) -> int:
        parameters = document["paths"][path]["get"]["parameters"]
        return int(next(one for one in parameters if one["name"] == "hours")["schema"]["maximum"])

    assert bound(MODELS) == bound(f"{API_PREFIX}/report/service-levels")


def test_the_providers_are_the_key_slots_and_no_answer_names_where_a_key_lives(
    client: TestClient, stored: Stored
) -> None:
    """Every provider slot is listed with its description, and no slot's environment variable
    name appears anywhere in the answer.

    Delete this and a later field can carry the variable a key is read from, which tells a
    reader of an administrative screen where the secret sits in the process."""
    response = get(client, "u_admin", MODELS)

    assert response.json()["providers"] == [
        {"provider": one.slug, "description": one.description} for one in PROVIDER_SLOTS
    ]
    for one in PROVIDER_SLOTS:
        assert one.env_var not in response.text
    assert "key_status_is_not_served" not in response.json()
    assert "breaker_state_is_not_recorded" not in response.json()


def test_fallbacks_fired_is_the_ledgers_sum_over_the_window_and_zero_when_nothing_fell_back(
    client: TestClient, stored: Stored
) -> None:
    """The figure is the database's coalesced sum over the same half-open window the lanes are
    counted over, and a sum over no rows is a measured zero rather than a missing figure.

    Delete this and "Fallbacks fired" can be drawn from a count the browser makes, or from a
    window other than the one printed beside it."""
    stored.fallbacks = 4
    assert get(client, "u_admin", MODELS).json()["fallbacks_fired"] == 4
    stored.fallbacks = None
    assert get(client, "u_admin", MODELS).json()["fallbacks_fired"] == 0

    start, end = datetime(2019, 3, 1, tzinfo=UTC), datetime(2019, 3, 8, tzinfo=UTC)
    compiled = fallbacks_between(start, end).compile(dialect=DIALECT)
    sql = str(compiled)
    assert "coalesce(sum(obs.request_telemetry.fallback_count)" in sql
    assert "obs.request_telemetry.received_at >=" in sql
    assert "obs.request_telemetry.received_at <" in sql
    assert start in compiled.params.values()
    assert end in compiled.params.values()


def test_every_tier_says_what_it_handles_in_the_order_the_chain_declares_it(
    client: TestClient, stored: Stored
) -> None:
    """One row per `Tier`, in declared order, each with a non-empty sentence.

    Delete this and a tier added to the chain is a row with no description, or no row at all on
    the screen that is supposed to explain the chain."""
    tiers = get(client, "u_admin", MODELS).json()["tiers"]

    assert set(TIER_HANDLES) == set(Tier)
    assert [one["tier"] for one in tiers] == [one.value for one in Tier]
    assert all(one["handles"].strip() for one in tiers)


def test_an_unmeasured_sentence_is_the_ledgers_own_and_leaves_when_the_ledger_fills_it(
    client: TestClient, stored: Stored
) -> None:
    """Each measurement the screen draws and the ledger cannot fill is answered with the ledger's
    own reason, and one the ledger has filled is not answered at all.

    Delete this and a console sentence saying no model is called outlives the commit that calls
    one, on the screen an administrator opens to see which model answered."""
    body = get(client, "u_admin", MODELS).json()

    assert body["unmeasured"] == [
        {"measure": one, "because": UNFILLABLE_TODAY[one]}
        for one in MEASURES_THE_MODELS_SCREEN_DRAWS
        if one in UNFILLABLE_TODAY
    ]
    assert body["unmeasured"] == []

    unfilled = {**UNFILLABLE_TODAY, **FILLED_BY_A_MODEL_CALL}
    assert [one.measure for one in unmeasured(unfilled)] == ["model", "provider", "fallback_count"]
    filled = {key: value for key, value in unfilled.items() if key != "provider"}
    assert [one.measure for one in unmeasured(filled)] == ["model", "fallback_count"]


# ------------------------------------------------------ the claims the answers make


def test_a_model_call_in_flight_is_written_by_the_executors_store_and_read_by_no_screen() -> None:
    """`ModelAttemptRow` is named by the package registering it and by the model service that
    writes and replays attempts, and by nothing this screen reads.

    Delete this and `requests_in_flight_are_not_recorded` stays true on the day the live runs
    route starts reading attempts, and the page goes on saying it cannot show what it could."""
    assert modules_using("ModelAttemptRow") == ["ops/model_service.py", "tables/__init__.py"]
    assert "operate_routes.py" not in modules_using("ModelAttemptRow")


def test_a_providers_health_is_replayed_from_attempts_and_stored_by_nothing() -> None:
    """`ProviderHealth` is named by the module defining it, the matrix that joins it, the replay
    that builds it from attempts and the executor walking with it, and by no store or table.

    Delete this and a second, stored copy of a breaker can be added beside the replayed one, and
    the screen and the executor can disagree about whether a provider is open."""
    assert modules_using("ProviderHealth") == [
        "console/model_matrix.py",
        "models/calls.py",
        "models/evidence.py",
        "models/health.py",
    ]


def test_the_queue_drivers_tables_are_secured_with_no_policy_and_nothing_cancels_a_queued_job() -> (
    None
):
    """The driver's security step creates no policy, so the application role reads no row, and
    nothing under `src/brain` calls the driver's cancellation.

    Delete this and `queue_is_not_readable` and `no_run_can_be_stopped` outlive a policy added to
    the queue or a cancellation wired to a route."""
    statements = driver_rls_statements(("procrastinate_jobs",))
    callers = modules_using("cancel_job_by_id") + modules_using("cancel_job_by_id_async")

    assert statements == ("ALTER TABLE ops.procrastinate_jobs ENABLE ROW LEVEL SECURITY",)
    assert callers == []


def test_this_router_offers_no_write_and_the_route_reads_no_credential(client: TestClient) -> None:
    """Every operation under `/operate` is a GET, and the route module imports nothing from the
    vault work.

    Delete this and a stop control or a key field can be added to these screens without a test
    saying what it reaches, which is the control `docs/admin-console.md` calls worse than none."""
    document = client.app.openapi()  # type: ignore[attr-defined]
    operations = {
        (path, method)
        for path, item in document["paths"].items()
        if path.startswith(f"{API_PREFIX}/operate")
        for method in item
    }
    imported = {
        node.module
        for node in ast.walk(ast.parse(inspect.getsource(operate_routes)))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert operations == {(RUNS, "get"), (MODELS, "get")}
    assert not {one for one in imported if "credential" in one}


def test_no_answer_carries_a_count_of_what_the_reader_was_not_shown() -> None:
    """No field on any view here is a name `brain.ops.jobs` recognises as a hidden count.

    Delete this and "showing 3 of 14 controls" arrives as a field somebody added for a footer."""
    views = (
        RunningControlView,
        OwedControlView,
        LiveRunsView,
        TierView,
        LaneTrafficView,
        ProviderView,
        UnmeasuredView,
        ModelsView,
    )

    found = [
        f"{view.__name__}.{name}"
        for view in views
        for name in view.model_fields
        if name in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
    ]

    assert found == []


def test_nothing_in_this_module_computes_a_reach() -> None:
    """There is no `intersect` call in the route module.

    Delete this and the console grows a second implementation of the platform's central rule in
    a file whose job is to load rows and copy an answer."""
    assert intersections_in(inspect.getsource(operate_routes)) == ()


def test_every_control_the_registry_declares_has_a_sentence_to_show() -> None:
    """Each control's `guards` is non-empty, so a row on the screen never shows a name alone.

    Delete this and a control added without a sentence renders as an identifier nobody outside
    this repository can read."""
    assert all(one.guards.strip() for one in CONTROLS)
