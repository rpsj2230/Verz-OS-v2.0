"""The three Report screens over HTTP: what each reader is shown, and what nothing says.

Driven through the real application, with the token machinery, the identity directory and the
key source imported from `tests/unit/test_api_routes.py` rather than rebuilt. What is under
test here is a scope and not an identity: the same people sign in the same way, and only what
their usage grant covers differs. A second copy of a JWS builder would be a second place for a
token to be minted subtly differently, and a test that failed for that reason would look like a
permission bug.

**The database is a stub session that answers by statement and never runs SQL.** This
repository has no PostgreSQL, so `async_sessionmaker(class_=...)` supplies a session whose
`execute` reads the compiled text of what it was handed and returns the rows that table holds.
That is honest about what it proves: the routes' wiring, the read modules' decisions over rows
built in memory and every response shape are exercised, and no WHERE clause is ever matched by
a server. `live_departments` is therefore also asserted as a compiled statement, which is the
part a stub cannot reach.

**The property most of this file exists for is that a narrowed answer is not visible as one.**
A department-scoped reader is shown a reading with no lanes, fewer spend lines and one adoption
line, and in each case the body is equal to the body an install with nothing in it produces.
There is no field anywhere saying a narrowing happened and none saying how much was left out,
and the tests that assert that are written over the whole key set rather than over the fields
somebody remembered.

Task ids: M27.7.15, M27.7.16, M27.7.17
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel, TrafficClass
from brain.ops.reliability import LANE_OBJECTIVES
from brain.ops.spend import Dimension
from brain.ops.telemetry import RequestStatus
from brain.report_routes import (
    DEFAULT_ADOPTION_LINES,
    MAX_ADOPTION_DAYS,
    MAX_ADOPTION_LINES,
    MAX_READING_HOURS,
    live_departments,
)
from brain.tables.adoption import QuestionAskedRow
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

SERVICE_LEVELS_PATH = f"{API_PREFIX}/report/service-levels"
SPEND_PATH = f"{API_PREFIX}/report/spend"
ADOPTION_PATH = f"{API_PREFIX}/report/adoption"

#: The grant every one of these screens is read behind. Written out rather than imported from
#: `brain.console.spend_view`, for the reason that module's own tests give about a constant
#: asserted against itself: read from there, this would move with it and the tests would stay
#: green for any capability at all. `test_the_screens_are_read_behind_the_usage_grant` compares
#: the two.
USAGE = "read:usage"

WHOLE = Scope.unrestricted()
#: One department, which is how a department admin's usage grant is written.
SUPPORT_ONLY = Scope(clauses=(Clause(field="department", op=Op.EQ, value="support"),))

#: A window's worth of days for the spend view's own grain.
DAY = date(2019, 3, 4)


def _grant(value: str, scope: Scope) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


#: What each of `test_api_routes`' people holds over usage. Deliberately unrelated to what
#: they hold over a price list: the point of reusing them is the token, not the grants.
REPORT_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": (_grant(USAGE, SUPPORT_ONLY),),
    "u_prefix": (_grant(USAGE, SUPPORT_ONLY),),
    "u_wide": (_grant(USAGE, WHOLE),),
    "u_admin": (_grant(USAGE, WHOLE),),
    "u_elsewhere": (),
}

#: An `amr` a Keycloak session carries when a second factor was used. A literal rather than a
#: value read out of the module that defines the set, which would compare it against itself.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


class ReportStore:
    """A `brain.gate.resolve.EntitlementStore` over `REPORT_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=REPORT_GRANTS[principal_id])


# ------------------------------------------------------------------- what the store holds
class SpendDailyRow:
    """One row of `ops.spend_daily` as the driver hands it back: attributes, not a model."""

    def __init__(self, department: str, key: str, cost_minor: int) -> None:
        self.day = DAY
        self.department = department
        self.principal_kind = PrincipalKind.HUMAN.value
        self.traffic = TrafficClass.HUMAN_INTERACTIVE.value
        self.dimension = Dimension.DEPARTMENT.value
        self.key = key
        self.cost_minor = cost_minor


class Stored:
    """Everything the stub session will answer, and every statement it was asked.

    One object per test, so one test's rows are never another test's evidence and the
    statements are inspectable afterwards.
    """

    def __init__(self) -> None:
        self.observations: tuple[tuple[Any, ...], ...] = ()
        self.refreshed_at: datetime | None = None
        self.spend_days: tuple[SpendDailyRow, ...] = ()
        self.departments: tuple[str, ...] = ()
        self.questions: tuple[QuestionAskedRow, ...] = ()
        self.statements: list[str] = []


_STORED = Stored()


class StubResult:
    """What `AsyncSession.execute` hands back, in the four shapes these routes read."""

    def __init__(self, rows: Sequence[Any], one: Any = None) -> None:
        self._rows = tuple(rows)
        self._one = one

    def scalars(self) -> StubResult:
        return self

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def scalar_one_or_none(self) -> Any:
        return self._one

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)


class StubSession(AsyncSession):
    """An `AsyncSession` that runs nothing, answers by table, and records every statement.

    Subclassed rather than faked, so `sessions_of`'s `isinstance` check is satisfied by the
    real factory type. That check is not scaffolding: it is what stops a bare test application
    answering 500 from an `AttributeError` that reads like a bug in the gate.

    Dispatching on the compiled text rather than on call order, because two of these routes
    read twice and a positional stub would answer the right rows to the wrong read the day
    somebody reordered them.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(statement)
        _STORED.statements.append(text)
        if "obs.request_telemetry" in text:
            return StubResult(_STORED.observations)
        if "ops.report_refresh" in text:
            return StubResult((), one=_STORED.refreshed_at)
        if "ops.spend_daily" in text:
            return StubResult(_STORED.spend_days)
        if "gate.department" in text:
            return StubResult(_STORED.departments)
        if "ops.question_asked" in text:
            return StubResult(_STORED.questions)
        msg = f"the stub session was asked something no report route reads: {text}"
        raise AssertionError(msg)

    async def commit(self) -> None:  # pragma: no cover - no report route writes
        msg = "a report route committed a transaction, and every one of them is a read"
        raise AssertionError(msg)

    async def close(self) -> None:
        return None


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store per test."""
    global _STORED
    _STORED = Stored()
    yield _STORED


@pytest.fixture
def client(stored: Stored) -> Iterator[TestClient]:
    """The real application, with a stub session factory where the pool would be.

    `create_app` produced everything else, including the router registration under test: a
    test that mounted the router itself would prove the routes work and not that they are
    served.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        # The lifespan built its console reads over whatever DATABASE_URL named, and CI names
        # a real database. Replacing the factory without this would read from there.
        app.state.console_reads = None
        yield c


@pytest.fixture
def unwired() -> Iterator[TestClient]:
    """The same application with no session factory, which is every deployment today."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        yield c


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=ReportStore(),
        cache=NoCache(),
    )


def get(c: TestClient, path: str, pid: str, **params: Any) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(path, headers={"authorization": f"Bearer {token}"}, params=params)
    return response


def observation(lane: Lane, *, status: RequestStatus, duration_ms: float) -> tuple[Any, ...]:
    """One row of `obs.request_telemetry` as `observed_between` selects it: four columns."""
    return (lane.value, status.value, duration_ms, datetime.now(UTC) - timedelta(minutes=5))


def question(trace: str, *, principal: str, department: str) -> QuestionAskedRow:
    """One stored question, dated inside every window these tests ask for."""
    row = QuestionAskedRow(
        trace_id=trace,
        principal_id=principal,
        principal_kind=PrincipalKind.HUMAN.value,
        channel=Channel.CONSOLE.value,
        department=department,
        at=datetime.now(UTC) - timedelta(hours=1),
    )
    return row


# --------------------------------------------------------------------- service levels
def test_a_reader_whose_usage_grant_covers_the_install_is_shown_every_declared_lane(
    client: TestClient, stored: Stored
) -> None:
    """The positive case, without which every refusal below is satisfied by refusing everybody.

    What breaks if this is deleted: a route that answered an empty reading to everybody would
    pass every disclosure test in this file, because an empty reading is exactly what a
    refused reader is supposed to get.
    """
    stored.observations = (
        observation(Lane.ANSWER, status=RequestStatus.ANSWERED, duration_ms=40.0),
        observation(Lane.FAST, status=RequestStatus.ANSWERED, duration_ms=5.0),
    )

    body = get(client, SERVICE_LEVELS_PATH, "u_wide").json()

    assert [one["lane"] for one in body["lanes"]] == [
        Lane.FAST.value,
        Lane.ANSWER.value,
        Lane.TASK.value,
    ]
    answered = next(one for one in body["lanes"] if one["lane"] == Lane.ANSWER.value)
    assert answered["requests"] == 1
    assert answered["success_rate"] == 1.0


def test_a_department_scoped_reader_is_shown_a_reading_with_no_lanes_at_all(
    client: TestClient, stored: Stored
) -> None:
    """A reading is the whole install's and has no department's version.

    What breaks if this is deleted: the install's request volume reaches a reader whose usage
    grant names one department, and the install's count less their own department's question
    count on the adoption screen is every other department's traffic, in one subtraction.
    """
    stored.observations = (
        observation(Lane.ANSWER, status=RequestStatus.ANSWERED, duration_ms=40.0),
    )

    body = get(client, SERVICE_LEVELS_PATH, "u_narrow").json()

    assert body["lanes"] == []


def test_a_narrowed_reading_and_the_reading_of_a_silent_install_are_the_same_body(
    client: TestClient, stored: Stored
) -> None:
    """DENIED and ABSENT, on this screen, are one object.

    What breaks if this is deleted: a field appears saying a narrowing happened, or an
    install with no objectives answers something a refused reader does not, and either way a
    reader can tell "you may not be told" from "there is nothing to tell".
    """
    stored.observations = (
        observation(Lane.ANSWER, status=RequestStatus.ANSWERED, duration_ms=40.0),
    )
    narrowed = get(client, SERVICE_LEVELS_PATH, "u_narrow").json()

    stored.observations = ()
    nothing_happened = get(client, SERVICE_LEVELS_PATH, "u_none").json()

    # Everything but the window, which is the request's own clock and differs between two
    # requests a millisecond apart whoever made them.
    assert _without_the_window(narrowed) == _without_the_window(nothing_happened)


def _without_the_window(body: dict[str, Any]) -> dict[str, Any]:
    """One reading's body with the instants taken off, so two requests can be compared."""
    return {key: value for key, value in body.items() if key not in {"start", "end"}}


def test_a_reading_carries_no_figure_about_what_it_did_not_show(
    client: TestClient, stored: Stored
) -> None:
    """Asserted over the whole key set rather than over the names somebody thought of.

    What breaks if this is deleted: a helpful field is added beside the lanes, `hidden`,
    `of_total` or a company request count, and nothing fails.
    """
    stored.observations = (
        observation(Lane.ANSWER, status=RequestStatus.ANSWERED, duration_ms=40.0),
    )

    body = get(client, SERVICE_LEVELS_PATH, "u_wide").json()

    assert set(body) == {"start", "end", "lanes"}
    assert set(body["lanes"][0]) == {
        "lane",
        "objective_p95_ms",
        "objective_success_rate",
        "p95_ms",
        "success_rate",
        "requests",
        "met",
        "shortfalls",
    }


def test_a_window_longer_than_the_bound_is_refused_identically_for_every_reader(
    client: TestClient, stored: Stored
) -> None:
    """The bound is a resource limit, so it cannot be read as a permission.

    What breaks if this is deleted: the bound is applied per caller, or applied after the
    read, and which windows somebody may ask for becomes a signal about what they may see.
    """
    admitted = get(client, SERVICE_LEVELS_PATH, "u_wide", hours=MAX_READING_HOURS + 1)
    refused = get(client, SERVICE_LEVELS_PATH, "u_none", hours=MAX_READING_HOURS + 1)

    assert admitted.status_code == 422
    assert refused.status_code == 422
    assert admitted.json() == refused.json()


# ------------------------------------------------------------------------------- spend
def test_a_reader_of_every_department_is_shown_every_line_and_a_total_of_exactly_those(
    client: TestClient, stored: Stored
) -> None:
    """The positive case for spend, and the total rule on the wire.

    What breaks if this is deleted: the total stops being the sum of the lines beside it, and
    the difference is the cost of rows the reader was not shown.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (
        SpendDailyRow("support", "support", 700),
        SpendDailyRow("finance", "finance", 300),
    )

    body = get(client, SPEND_PATH, "u_wide").json()

    assert body["built"] is True
    assert {one["key"]: one["cost_minor"] for one in body["lines"]} == {
        "support": 700,
        "finance": 300,
    }
    assert body["total_minor"] == sum(one["cost_minor"] for one in body["lines"])


def test_a_department_scoped_reader_is_shown_their_own_line_and_a_total_of_only_it(
    client: TestClient, stored: Stored
) -> None:
    """The refusal sibling: fewer lines, and a total that reconciles against them.

    What breaks if this is deleted: a narrowed report keeps the company's total, and one
    subtraction gives the reader every other department's spend.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (
        SpendDailyRow("support", "support", 700),
        SpendDailyRow("finance", "finance", 300),
    )

    body = get(client, SPEND_PATH, "u_narrow").json()

    assert [one["key"] for one in body["lines"]] == ["support"]
    assert body["total_minor"] == 700


def test_a_view_nobody_has_refreshed_is_answered_as_unbuilt_rather_than_as_no_spend(
    client: TestClient, stored: Stored
) -> None:
    """A report over nothing says the company spent nothing, which is a figure and a false one.

    What breaks if this is deleted: a fresh install shows every department a total of zero
    and a freshness nobody can act on, which is the screen a person reads before deciding not
    to worry.
    """
    stored.refreshed_at = None
    stored.spend_days = ()

    body = get(client, SPEND_PATH, "u_wide").json()

    assert body["built"] is False
    assert body["total_minor"] is None
    assert body["lines"] == []
    assert body["freshness"] == "unstated"


def test_a_spend_report_carries_no_field_counting_what_it_did_not_show(
    client: TestClient, stored: Stored
) -> None:
    """The key set again, for the screen where a residual bucket is most tempting.

    What breaks if this is deleted: `others`, `company_total` or a share arrives beside a
    filtered breakdown, which is the hidden figure with a percent sign on it.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (SpendDailyRow("support", "support", 700),)

    body = get(client, SPEND_PATH, "u_narrow").json()

    assert set(body) == {
        "dimension",
        "built",
        "lines",
        "machine_included",
        "total_minor",
        "as_of",
        "freshness",
    }


def test_the_report_says_whether_machine_traffic_was_counted(
    client: TestClient, stored: Stored
) -> None:
    """The qualifier is a field rather than a caption, and the default excludes automation.

    What breaks if this is deleted: a nightly sync's cost is counted silently, and the screen
    answers "what does this cost" with the price of a schedule.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (SpendDailyRow("support", "support", 700),)

    assert get(client, SPEND_PATH, "u_wide").json()["machine_included"] is False
    assert (
        get(client, SPEND_PATH, "u_wide", include_machine=True).json()["machine_included"] is True
    )


def test_a_window_the_caller_names_reaches_the_read_module_rather_than_being_dropped(
    client: TestClient, stored: Stored
) -> None:
    """A parameter the route declares and never passes on is discarded in silence.

    What breaks if this is deleted: `since` stops being handed to the read module, FastAPI
    accepts it, nothing fails, and a person reading a week is shown the whole retained history
    under a heading that says otherwise.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (SpendDailyRow("support", "support", 700),)

    inside = get(client, SPEND_PATH, "u_wide", since=DAY.isoformat())
    after = get(client, SPEND_PATH, "u_wide", since=(DAY + timedelta(days=1)).isoformat())

    assert inside.json()["lines"] == [{"key": "support", "cost_minor": 700}]
    assert after.json()["lines"] == []


def test_the_dimension_asked_for_is_the_dimension_grouped_and_the_one_the_answer_names(
    client: TestClient, stored: Stored
) -> None:
    """The parameter decides both the rows read and the word on the page.

    What breaks if this is deleted: the answer is headed with one dimension and grouped by
    another, which is a page of models under the word department and no way to tell.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    by_model = SpendDailyRow("support", "a-model", 500)
    by_model.dimension = Dimension.MODEL.value
    stored.spend_days = (SpendDailyRow("support", "support", 700), by_model)

    body = get(client, SPEND_PATH, "u_wide", dimension=Dimension.MODEL.value).json()

    assert body["dimension"] == Dimension.MODEL.value
    assert body["lines"] == [{"key": "a-model", "cost_minor": 500}]


# ---------------------------------------------------------------------------- adoption
def test_every_department_the_reader_reaches_gets_a_line_including_one_with_no_questions(
    client: TestClient, stored: Stored
) -> None:
    """A line's presence is a fact about the reader's reach and never about what happened.

    What breaks if this is deleted: departments with nothing recorded vanish from the page,
    and which departments appear becomes a report on who has been quiet.
    """
    stored.departments = ("finance", "support")
    stored.questions = (question("t1", principal="p1", department="support"),)

    body = get(client, ADOPTION_PATH, "u_wide").json()

    assert [one["department"] for one in body["items"]] == ["finance", "support"]
    assert [one["questions"] for one in body["items"]] == [0, 1]
    assert [one["people"] for one in body["items"]] == [0, 1]


def test_a_department_scoped_reader_is_shown_one_line_and_no_sign_of_the_others(
    client: TestClient, stored: Stored
) -> None:
    """The refusal sibling for adoption.

    What breaks if this is deleted: the department list on this page becomes the company's org
    chart, handed to a reader whose grant names one department.
    """
    stored.departments = ("finance", "support")
    stored.questions = (
        question("t1", principal="p1", department="support"),
        question("t2", principal="p2", department="finance"),
    )

    body = get(client, ADOPTION_PATH, "u_narrow").json()

    assert [one["department"] for one in body["items"]] == ["support"]
    assert body["total"] is None
    assert body["truncated"] is False


def test_a_full_page_of_adoption_says_there_is_more_and_never_how_much(
    client: TestClient, stored: Stored
) -> None:
    """`truncated` is a flag, and there is no arithmetic anywhere on the page.

    What breaks if this is deleted: a count arrives beside a bounded listing, and the reader
    learns the size of a set they were shown part of.
    """
    stored.departments = ("finance", "support")

    body = get(client, ADOPTION_PATH, "u_wide", limit=1).json()

    assert body["truncated"] is True
    assert len(body["items"]) == 1
    assert body["total"] is None


def test_an_adoption_line_carries_three_figures_and_nowhere_for_a_fourth(
    client: TestClient, stored: Stored
) -> None:
    """The key set, held to `brain.adoption.DepartmentAdoption`'s own three fields.

    What breaks if this is deleted: a figure the adoption module refuses to hold is added one
    layer out, where the argument against it is not written down.
    """
    stored.departments = ("support",)
    stored.questions = (question("t1", principal="p1", department="support"),)

    body = get(client, ADOPTION_PATH, "u_wide").json()

    assert set(body["items"][0]) == {"department", "questions", "people"}


def test_an_adoption_window_longer_than_the_bound_is_refused_identically_for_every_reader(
    client: TestClient, stored: Stored
) -> None:
    """The same resource bound, on the other window.

    What breaks if this is deleted: one request asks for every question the store has ever
    held and groups them in one process.
    """
    admitted = get(client, ADOPTION_PATH, "u_wide", days=MAX_ADOPTION_DAYS + 1)
    refused = get(client, ADOPTION_PATH, "u_none", days=MAX_ADOPTION_DAYS + 1)

    assert admitted.status_code == 422
    assert admitted.json() == refused.json()


# ------------------------------------------------------------------ what they share
def test_a_process_with_no_database_answers_every_reader_the_same_fault(
    unwired: TestClient,
) -> None:
    """A reader admitted everything and a reader admitted nothing get one answer.

    What breaks if this is deleted: the routes grow a capability check in front of the
    database, the refused reader stops reaching it, and the difference between the two
    answers publishes whether this deployment has a pool to anybody who can reach the port.
    """
    for path in (SERVICE_LEVELS_PATH, SPEND_PATH, ADOPTION_PATH):
        admitted = get(unwired, path, "u_wide")
        refused = get(unwired, path, "u_none")
        assert admitted.status_code == refused.status_code
        assert admitted.json()["message"] == refused.json()["message"]


def test_a_reader_holding_no_usage_grant_is_answered_an_empty_report_and_never_a_refusal(
    client: TestClient, stored: Stored
) -> None:
    """Holding nothing is an empty answer, which is what all three read modules argue for.

    What breaks if this is deleted: a refusal naming the grant tells a reader that a usage
    report exists and that they were measured against it.
    """
    stored.refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    stored.spend_days = (SpendDailyRow("support", "support", 700),)
    stored.departments = ("support",)

    spend = get(client, SPEND_PATH, "u_none")
    adoption = get(client, ADOPTION_PATH, "u_none")

    assert spend.status_code == 200
    assert spend.json()["lines"] == []
    assert spend.json()["total_minor"] == 0
    assert adoption.status_code == 200
    assert adoption.json()["items"] == []


def test_the_screens_are_read_behind_the_grant_the_usage_screen_requires(
    client: TestClient, stored: Stored
) -> None:
    """The capability these tests grant is the one the console registry names, compared not derived.

    What breaks if this is deleted: this file grants a capability nothing else uses, every
    test above passes, and the routes are exercised behind a grant no real reader holds.
    """
    from brain.console.screens import screen
    from brain.console.spend_view import USAGE_AUTHORITY

    assert USAGE_AUTHORITY.value == USAGE
    assert screen("usage").read.requires.value == USAGE
    assert screen("service_levels").read.requires.value == USAGE


def test_the_department_list_a_page_is_built_from_holds_only_live_rows(
    stored: Stored,
) -> None:
    """The statement, compiled, because a stub session matches no WHERE clause.

    What breaks if this is deleted: a retired department keeps a line on the adoption page for
    ever, and the one thing a stub cannot catch is exactly this.
    """
    compiled = str(live_departments())

    assert "gate.department" in compiled
    assert "deleted_at IS NULL" in compiled
    assert "ORDER BY gate.department.slug" in compiled
    assert "gate.department.name" not in compiled


def test_the_routes_read_the_store_before_they_narrow_it(
    client: TestClient, stored: Stored
) -> None:
    """A refused reader asks the store exactly what a permitted reader asks it.

    What breaks if this is deleted: a route returns early for a reader it expects to be
    refused, and that reader becomes the one whose request to a broken database succeeds,
    which is a difference anybody can time from outside.
    """
    stored.departments = ("support",)
    get(client, ADOPTION_PATH, "u_none")
    refused = list(stored.statements)

    stored.statements.clear()
    get(client, ADOPTION_PATH, "u_wide")

    assert [_table_of(one) for one in refused] == [_table_of(one) for one in stored.statements]


def _table_of(statement: str) -> str:
    """Which table a compiled statement names, for comparing two reads without their text."""
    for name in ("gate.department", "ops.question_asked", "obs.request_telemetry"):
        if name in statement:
            return name
    return "unrecognised"


def test_the_page_a_console_asks_for_by_default_is_one_the_route_admits(
    client: TestClient, stored: Stored
) -> None:
    """The default is inside the bound, asserted against the bound rather than against itself.

    What breaks if this is deleted: the two constants drift apart, and a console asking for
    the default is refused with a validation error on every single load, whose body is
    `HTTPValidationError` and reaches a person as the least useful sentence this console has.
    """
    stored.departments = ("support",)

    assert DEFAULT_ADOPTION_LINES <= MAX_ADOPTION_LINES
    assert get(client, ADOPTION_PATH, "u_wide", limit=DEFAULT_ADOPTION_LINES).status_code == 200


def test_a_reading_names_the_objective_it_was_measured_against(
    client: TestClient, stored: Stored
) -> None:
    """The promise and the measurement arrive together, so the gap needs no second document.

    What breaks if this is deleted: the screen shows a p95 with nothing to compare it to, and
    whether a lane met what it promised becomes something the browser works out.
    """
    stored.observations = (
        observation(Lane.ANSWER, status=RequestStatus.ANSWERED, duration_ms=40.0),
    )

    body = get(client, SERVICE_LEVELS_PATH, "u_wide").json()
    answered = next(one for one in body["lanes"] if one["lane"] == Lane.ANSWER.value)
    declared = next(one for one in LANE_OBJECTIVES if one.lane is Lane.ANSWER)

    assert answered["objective_p95_ms"] == declared.p95_ms
    assert answered["objective_success_rate"] == declared.success_rate


def test_a_lane_that_missed_its_objective_says_so_in_the_reliability_modules_own_words(
    client: TestClient, stored: Stored
) -> None:
    """`met` is the reading's verdict, carried, and the shortfalls are carried with it.

    What breaks if this is deleted: the route reports every lane as meeting its objective, or
    composes a sentence of its own about the gap, and the screen that exists to show a promise
    being missed shows nothing at all.
    """
    stored.observations = tuple(
        observation(Lane.ANSWER, status=RequestStatus.NOTHING_RETURNED, duration_ms=40.0)
        for _ in range(10)
    )

    body = get(client, SERVICE_LEVELS_PATH, "u_wide").json()
    answered = next(one for one in body["lanes"] if one["lane"] == Lane.ANSWER.value)

    assert answered["met"] is False
    assert answered["shortfalls"] != []
