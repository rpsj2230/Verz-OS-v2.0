"""Usage, questions and quality over HTTP: what each reader is shown, and what the responses say.

Driven through the real application, with the token machinery and the identity directory
imported from `tests/unit/test_api_routes.py` rather than rebuilt, for the reason
`tests/unit/test_report_routes.py` gives. What differs between readers here is a grant's scope
and nothing else.

**The database is a stub session that answers by table and never runs SQL**, as in that file,
so what is proved is the wiring, the read modules' decisions over rows built in memory and the
shape of every response, and the two statements that matter are asserted as compiled SQL.

**The property most of this file exists for is that a withheld answer is not visible as one.**
A reader who may not be told that nothing is connected gets the body a connected install gives,
a reader who may not see the last canary run gets the body an install with no run gives, and a
reader holding no usage grant gets tables that are absent rather than empty. Each is asserted
over whole bodies rather than over fields somebody remembered.

Task ids: M27.7.14, M27.7.18, M27.7.19
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain import report_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.identity.bearer import TokenAuthority
from brain.ops.schedule_runner import Runner, runner_for
from brain.report_routes import DEFAULT_USAGE_DAYS, MAX_USAGE_DAYS, last_canary_run
from brain.tables.adoption import QuestionAskedRow
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SOURCE,
    Directory,
    Keys,
    NoCache,
    UnfilteredRows,
    Versions,
    token_for,
    verifier,
)

USAGE_PATH = f"{API_PREFIX}/report/usage"
QUESTIONS_PATH = f"{API_PREFIX}/report/questions"
QUALITY_PATH = f"{API_PREFIX}/report/quality"

#: The grants, written out rather than read from the read modules, so a capability moved in one
#: place is a failing test rather than a constant agreeing with itself.
USAGE = "read:usage"
QUESTION = "read:question"
EVALUATION = "read:evaluation"
AGENT = "read:agent"

WHOLE = Scope.unrestricted()
SUPPORT = Scope.department("support")


def _held(scope: Scope, *capabilities: str) -> tuple[Grant, ...]:
    return tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities)


#: What each of `test_api_routes`' people holds on these three screens.
SCREEN_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_wide": _held(WHOLE, USAGE, QUESTION, EVALUATION, AGENT),
    "u_narrow": _held(SUPPORT, USAGE, QUESTION, EVALUATION),
    "u_prefix": _held(WHOLE, QUESTION),
    "u_none": (),
    "u_admin": (),
    "u_elsewhere": (),
}

#: The `amr` a session with a second factor carries, as a literal.
SECOND_FACTOR = {"amr": ["otp"]}

#: The two sentences an asker receives, as literals.
NOTHING_CONNECTED = "Nothing I can reach is connected to that yet, so I have not guessed."
NOTHING_FOUND = "I could not find that."


class ScreenStore:
    """A `brain.gate.resolve.EntitlementStore` over `SCREEN_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=SCREEN_GRANTS[principal_id])


class Stored:
    """What the stub session answers, and every statement it was handed."""

    def __init__(self) -> None:
        self.departments: tuple[str, ...] = ()
        self.questions: tuple[QuestionAskedRow, ...] = ()
        self.canary_runs: tuple[tuple[Any, ...], ...] = ()
        self.statements: list[str] = []


_STORED = Stored()


class StubResult:
    """What `AsyncSession.execute` hands back, in the shapes these routes read."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def scalars(self) -> StubResult:
        return self

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class StubSession(AsyncSession):
    """An `AsyncSession` that runs nothing, answers by table, and records every statement."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(statement)
        _STORED.statements.append(text)
        if "gate.department" in text:
            return StubResult(_STORED.departments)
        if "ops.question_asked" in text:
            return StubResult(_STORED.questions)
        if "ops.control_run" in text:
            return StubResult(_STORED.canary_runs)
        msg = f"the stub session was asked something these routes do not read: {text}"
        raise AssertionError(msg)

    async def commit(self) -> None:  # pragma: no cover - no report route writes
        msg = "a report route committed a transaction, and every one of them is a read"
        raise AssertionError(msg)

    async def close(self) -> None:
        return None


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=ScreenStore(),
        cache=NoCache(),
    )


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store per test."""
    global _STORED
    _STORED = Stored()
    yield _STORED


@pytest.fixture
def client(stored: Stored) -> Iterator[TestClient]:
    """The real application, a stub session factory, and a registry with nothing connected.

    `build_registry` with no records registers no row tool, which is the registry a process
    holds when no source is connected, and the answer lane abstains with nothing connected
    over exactly that registry.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        app.state.tools = build_registry(source=SOURCE)
        yield c


@pytest.fixture
def connected(stored: Stored) -> Iterator[TestClient]:
    """The same application with row tools registered, which is a connected source."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        app.state.tools = build_registry(source=SOURCE, records=UnfilteredRows())
        yield c


@pytest.fixture
def unwired() -> Iterator[TestClient]:
    """No session factory and no registry, which is a process that can answer none of these."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        app.state.tools = None
        yield c


def get(c: TestClient, path: str, pid: str, **params: Any) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(path, headers={"authorization": f"Bearer {token}"}, params=params)
    return response


def question(
    trace: str, *, principal: str, department: str, kind: PrincipalKind = PrincipalKind.HUMAN
) -> QuestionAskedRow:
    """One stored question, dated inside every window these tests ask for."""
    return QuestionAskedRow(
        trace_id=trace,
        principal_id=principal,
        principal_kind=kind.value,
        channel=Channel.CONSOLE.value,
        department=department,
        at=datetime.now(UTC) - timedelta(hours=1),
    )


def seed_questions(stored: Stored) -> None:
    stored.departments = ("support", "web")
    stored.questions = (
        question("t1", principal="u_ana", department="support"),
        question("t2", principal="u_ana", department="support"),
        question("t3", principal="u_ben", department="support"),
        question("t4", principal="u_cai", department="web"),
        question("t5", principal="u_job", department="web", kind=PrincipalKind.SERVICE),
    )


# ----------------------------------------------------------------------------------- usage
def test_a_company_wide_reader_is_shown_questions_by_department_and_by_person(
    client: TestClient, stored: Stored
) -> None:
    """The positive case, without which every narrowing below is satisfied by showing nothing.

    What breaks if this is deleted: a route that answered every reader absent tables would pass
    the rest of this section, because absent tables are what a reader holding nothing gets.
    """
    seed_questions(stored)

    body = get(client, USAGE_PATH, "u_wide").json()

    assert body["departments"] == [
        {"department": "support", "questions": 3, "people": 2},
        {"department": "web", "questions": 1, "people": 1},
    ]
    assert body["people"] == [
        {"person": "u_ana", "questions": 2},
        {"person": "u_ben", "questions": 1},
        {"person": "u_cai", "questions": 1},
    ]
    assert body["questions"] == 4
    assert body["machine_included"] is False
    assert body["not_measured"] == ["tokens", "model", "agent"]


def test_a_department_scoped_reader_is_shown_that_department_on_both_tables(
    client: TestClient, stored: Stored
) -> None:
    """Narrowed on the person table as well as the department table.

    What breaks if this is deleted: a department admin reads the names of the people asking in
    every other department off the person table.
    """
    seed_questions(stored)

    body = get(client, USAGE_PATH, "u_narrow").json()

    assert body["departments"] == [{"department": "support", "questions": 3, "people": 2}]
    assert [one["person"] for one in body["people"]] == ["u_ana", "u_ben"]
    assert body["questions"] == 3
    assert body["not_measured"] == ["tokens", "model"]


@pytest.mark.parametrize("pid", ["u_none", "u_prefix"])
def test_a_reader_holding_no_usage_grant_is_shown_no_table_and_never_a_refusal(
    client: TestClient, stored: Stored, pid: str
) -> None:
    """Absent tables, no total, no sentence, and a 200.

    What breaks if this is deleted: a refusal naming the usage grant tells a reader a usage
    report exists, or a zero total is a false figure about the company.
    """
    seed_questions(stored)

    response = get(client, USAGE_PATH, pid)

    assert response.status_code == 200
    body = response.json()
    assert (body["departments"], body["people"], body["questions"]) == (None, None, None)
    assert body["not_measured"] == []


def test_the_usage_response_carries_no_field_a_hidden_count_could_arrive_in(
    client: TestClient, stored: Stored
) -> None:
    """The key set, whole, for a wide reader and a narrow one.

    What breaks if this is deleted: a helpful `excluded` or `others` field is added beside the
    tables, and it is the size of what the narrow reader was not shown.
    """
    seed_questions(stored)

    for pid in ("u_wide", "u_narrow", "u_none"):
        body = get(client, USAGE_PATH, pid).json()
        assert set(body) == {
            "start",
            "end",
            "departments",
            "people",
            "questions",
            "machine_included",
            "not_measured",
        }


def test_the_usage_window_defaults_to_a_week_and_is_bounded_for_everybody(
    client: TestClient, stored: Stored
) -> None:
    """The bound is a resource limit, identical for a reader admitted everything and nothing.

    What breaks if this is deleted: a request for ten years reads every question the ledger holds
    in one process, or the bound differs between readers and tells them apart.
    """
    seed_questions(stored)

    body = get(client, USAGE_PATH, "u_wide").json()
    start = datetime.fromisoformat(body["start"])
    end = datetime.fromisoformat(body["end"])
    assert end - start == timedelta(days=DEFAULT_USAGE_DAYS)
    assert DEFAULT_USAGE_DAYS == 7
    assert MAX_USAGE_DAYS == 366

    for pid in ("u_wide", "u_none"):
        assert get(client, USAGE_PATH, pid, days=MAX_USAGE_DAYS).status_code == 200
        assert get(client, USAGE_PATH, pid, days=MAX_USAGE_DAYS + 1).status_code == 422
        assert get(client, USAGE_PATH, pid, days=0).status_code == 422


def test_usage_reads_the_directory_and_then_the_questions_for_every_reader(
    client: TestClient, stored: Stored
) -> None:
    """A reader offered nothing does the same two reads as a reader offered everything.

    What breaks if this is deleted: the route returns early for a reader it expects to refuse,
    and that reader is the one whose request to a broken process succeeds.
    """
    seed_questions(stored)

    for pid in ("u_wide", "u_none"):
        stored.statements.clear()
        get(client, USAGE_PATH, pid)
        assert ["gate.department" in one for one in stored.statements] == [True, False]
        assert "ops.question_asked" in stored.statements[1]


# ------------------------------------------------------------------------------- questions
@pytest.mark.parametrize("pid", ["u_wide", "u_narrow", "u_prefix"])
def test_any_holder_of_the_questions_grant_is_told_nothing_is_connected(
    client: TestClient, pid: str
) -> None:
    """Whatever the scope, because every asker in the company is told the same sentence.

    What breaks if this is deleted: an administrator whose staff are all being answered with
    nothing connected opens this screen and reads nothing about it.
    """
    body = get(client, QUESTIONS_PATH, pid).json()

    assert body == {
        "nothing_connected": True,
        "answered_when_nothing_connected": NOTHING_CONNECTED,
        "answered_when_nothing_found": NOTHING_FOUND,
        "unanswered_are_recorded": False,
    }


def test_a_connected_install_names_no_gap(connected: TestClient) -> None:
    """The registry the answer lane reads holds a row reader, so no asker is told nothing is.

    What breaks if this is deleted: a route that said nothing was connected to everybody passes
    the test above, and a connected install is told to connect a source.
    """
    assert get(connected, QUESTIONS_PATH, "u_wide").json()["nothing_connected"] is False


def test_a_reader_without_the_questions_grant_gets_the_body_a_connected_install_gives(
    client: TestClient, connected: TestClient
) -> None:
    """DENIED and ABSENT, as two whole bodies.

    What breaks if this is deleted: a reader holding nothing reads off the response whether the
    install has anything connected.
    """
    refused = get(client, QUESTIONS_PATH, "u_none")
    nothing_to_say = get(connected, QUESTIONS_PATH, "u_wide")

    assert refused.status_code == nothing_to_say.status_code == 200
    assert refused.json() == nothing_to_say.json()


def test_questions_reads_no_database(client: TestClient, stored: Stored) -> None:
    """Nothing on a database records how a question ended, so nothing is read from one.

    What breaks if this is deleted: a query against the question ledger is added to count
    something the screen argues must not be counted, and nothing notices.
    """
    get(client, QUESTIONS_PATH, "u_wide")

    assert stored.statements == []


# --------------------------------------------------------------------------------- quality
def test_a_whole_install_evaluation_reader_is_shown_the_last_canary_run(
    client: TestClient, stored: Stored
) -> None:
    """The positive case, and the state is the attempt table's word and never passed.

    What breaks if this is deleted: every withholding test below is satisfied by a route that
    shows nobody a run, and `ok` could reach the page as a pass.
    """
    started = datetime(2019, 3, 5, 6, 0, tzinfo=UTC)
    stored.canary_runs = ((started, started + timedelta(minutes=2), "ok"),)

    body = get(client, QUALITY_PATH, "u_wide").json()

    assert body["last_canary_run"] == {
        "started_at": "2019-03-05T06:00:00Z",
        "finished_at": "2019-03-05T06:02:00Z",
        "state": "finished",
    }
    assert body["canary_interval_seconds"] == 12 * 60 * 60
    assert body["findings_are_recorded"] is False
    assert body["evaluation_runs_are_recorded"] is False
    assert "pass" not in str(body).lower()


@pytest.mark.parametrize("pid", ["u_narrow", "u_none", "u_prefix"])
def test_a_reader_who_may_not_see_a_run_gets_the_body_of_an_install_with_none(
    client: TestClient, stored: Stored, pid: str
) -> None:
    """A department-scoped evaluation grant included, because a failed run is a way in.

    What breaks if this is deleted: a department admin, or somebody holding nothing, learns that
    the gate failed its canaries, and the two bodies differ by exactly that.
    """
    never_run = get(client, QUALITY_PATH, "u_wide").json()
    started = datetime(2019, 3, 5, 6, 0, tzinfo=UTC)
    stored.canary_runs = ((started, started + timedelta(minutes=2), "failed"),)

    withheld = get(client, QUALITY_PATH, pid)

    assert withheld.status_code == 200
    assert withheld.json() == never_run
    assert never_run["last_canary_run"] is None


def test_the_quality_screen_says_whether_anything_starts_the_canaries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the runner the worker itself looks up, in both states.

    What breaks if this is deleted: the page says the canaries run on a cadence on an install
    where nothing starts them, or goes on saying nothing does after a runner is wired.
    """
    assert get(client, QUALITY_PATH, "u_wide").json()["canaries_started"] is (
        runner_for("canary_run").run is not None
    )

    wired = Runner(name="canary_run", run=lambda now, report_only, url: "ran")
    monkeypatch.setattr(report_routes, "runner_for", lambda name: wired)

    assert get(client, QUALITY_PATH, "u_none").json()["canaries_started"] is True


def test_the_canary_run_statement_selects_no_detail_and_takes_the_newest_start() -> None:
    """The statement, compiled, because the stub cannot match a WHERE clause.

    What breaks if this is deleted: the detail column, where a finding's field name would be
    written, is selected onto a path whose reader may not know that field exists, or an older
    finished run stands in for a newer one that never returned.
    """
    statement = last_canary_run()
    compiled = str(statement)

    assert compiled.startswith(
        "SELECT ops.control_run.started_at, ops.control_run.finished_at, ops.control_run.outcome"
    )
    assert "detail" not in compiled
    assert "WHERE ops.control_run.name = :name_1" in compiled
    assert "ORDER BY ops.control_run.started_at DESC" in compiled
    assert "LIMIT :param_1" in compiled
    assert statement.compile().params == {"name_1": "canary_run", "param_1": 1}


# ------------------------------------------------------------------------------- unwired
@pytest.mark.parametrize("path", [USAGE_PATH, QUESTIONS_PATH, QUALITY_PATH])
def test_a_process_that_cannot_answer_says_so_identically_to_every_reader(
    unwired: TestClient, path: str
) -> None:
    """No pool and no registry is a fault, and a refused reader meets the same fault.

    What breaks if this is deleted: a capability check in front of the read means the refused
    reader never reaches the fault, and the difference publishes whether the process is wired.
    """
    admitted = get(unwired, path, "u_wide")
    refused = get(unwired, path, "u_none")

    assert admitted.status_code == refused.status_code == 500
    assert admitted.json()["message"] == refused.json()["message"]
