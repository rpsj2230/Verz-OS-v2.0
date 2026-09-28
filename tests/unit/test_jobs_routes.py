"""The Scheduled jobs screen over HTTP: what each job shows, and the three controls that reach the
worker's tick.

Driven through the real application with the run records and `ops.setting` held in memory. A
control is followed to the row the tick reads (`tests/unit/test_schedule_control.py` follows that
row into the tick), and every refusal has a sibling proving the same control works for somebody
who may use it.

Task ids: M27.8.13, M27.15.47
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.jobs_routes import (
    JOB_PERIODS,
    RUN_HISTORY_LOAD,
    SCHEDULE_AUTHORITY,
    SWITCHED_OFF,
    failure_kind,
)
from brain.ops.controls import control
from brain.ops.schedule import schedulable
from brain.ops.schedule_runner import RUNNERS
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result, Row, SettingRows

JOBS = f"{API_PREFIX}/jobs"
REFRESH = "spend_report_refresh"
UNWIRED = next(one.name for one in RUNNERS if one.run is None)
EVERYWHERE = Scope.unrestricted()
QUEUE_READ = screen("queue").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)

#: `u_admin` may see and control every job. `u_wide` may see and not control. `u_narrow` holds the
#: authority and may not see a job, so may not control one either. `u_elsewhere` sees every job
#: and holds the authority in one department, which the whole install's schedule is not.
GRANTS = {
    "u_admin": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
        Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),
    ),
    "u_wide": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_narrow": (Grant(capability=SCHEDULE_AUTHORITY, scope=EVERYWHERE),),
    "u_elsewhere": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
        Grant(capability=SCHEDULE_AUTHORITY, scope=Scope.department("finance")),
    ),
    "u_none": (),
}


class Success(NamedTuple):
    name: str
    finished_at: datetime


class Figures(Result):
    """The one counting row `figures_of` selects, read by its labels."""

    def __init__(self, counted: dict[str, int]) -> None:
        super().__init__([])
        self.counted = counted

    def mappings(self) -> Figures:
        return self

    def one(self) -> dict[str, int]:
        return self.counted


class Person(NamedTuple):
    id: str
    display_name: str


class Runs:
    """The run records the stub answers with: each control's newest run, its last success, one
    job's past runs and its figures, and the display names of the people rows name."""

    def __init__(self) -> None:
        self.newest: list[tuple[str, datetime, datetime | None, str | None, str | None]] = []
        self.successes: dict[str, datetime] = {}
        self.past: list[
            tuple[uuid.UUID, datetime, datetime | None, str | None, bool, str | None]
        ] = []
        self.figures: dict[str, int] = {
            f"{figure}_{range_}": 0
            for figure in ("started", "succeeded", "failed", "reported_only")
            for range_, _ in JOB_PERIODS
        }
        self.names = {"u_admin": "Ada Admin"}

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        columns = [one["name"] for one in statement.column_descriptions]
        if columns == ["name", "started_at", "finished_at", "outcome", "detail"]:
            return Result(Row(one) for one in self.newest)
        if columns == ["name", "finished_at"]:
            return Result(Success(n, at) for n, at in self.successes.items())
        if columns == ["id"]:
            return Result([])
        if columns == ["id", "started_at", "finished_at", "outcome", "report_only", "detail"]:
            return Result(Row(one) for one in self.past)
        if columns and columns[0].startswith("started_"):
            return Figures(self.figures)
        if columns == ["PrincipalRow"]:
            asked = statement.compile().params["id_1"]
            return Result(Person(one, self.names[one]) for one in asked if one in self.names)
        return None


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def runs() -> Runs:
    return Runs()


@pytest.fixture
def served(settings: SettingRows, runs: Runs) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, runs.answer])
        yield client, stub


def switched_on(settings: SettingRows) -> None:
    settings.hold("feature.schedule_control", True, value_type="boolean", by="u_admin")


def job(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(one for one in body["jobs"] if one["control"] == name)


# ------------------------------------------------------------------------ the list


def test_a_reader_of_the_queue_sees_every_scheduled_job_with_what_it_keeps_true(
    served: tuple[TestClient, Stub],
) -> None:
    """Every job the worker ticks, in registry order, with the registry's sentence and whether
    its runner can start.

    Delete this and every refusal below is satisfied by a route that lists nothing."""
    client, _ = served
    body = get(client, "u_wide", JOBS).json()

    assert [one["control"] for one in body["jobs"]] == [one.name for one in schedulable()]
    assert job(body, REFRESH)["keeps_true"] == control(REFRESH).guards
    assert job(body, REFRESH)["runnable"] is True
    assert job(body, UNWIRED)["runnable"] is False
    assert "nothing to run yet" in job(body, UNWIRED)["needs"]
    assert body["may_control"] is False
    assert body["controls_switched_on"] is False


def test_a_reader_without_the_queue_grant_is_answered_the_list_of_an_install_with_no_schedule(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a caller who may not see the schedule reads every job and how it went."""
    client, _ = served
    for pid in ("u_none", "u_narrow"):
        body = get(client, pid, JOBS).json()
        assert body["jobs"] == []


def test_a_failed_run_is_shown_by_its_kind_and_never_its_message(
    served: tuple[TestClient, Stub], runs: Runs
) -> None:
    """The message of a failure can quote a value, so only the exception type is served, and a
    finished run's report is served whole.

    Delete this and a database refusal quoting somebody's email address reaches the console."""
    client, _ = served
    started = datetime.now(UTC) - timedelta(minutes=5)
    runs.newest = [
        (
            REFRESH,
            started,
            started + timedelta(seconds=2),
            "failed",
            "IntegrityError: Key (email)=(a@b.c)",
        ),
        ("knowledge_reverification", started, started, "ok", "Nothing was overdue."),
    ]
    body = get(client, "u_wide", JOBS).json()

    failed = job(body, REFRESH)
    assert failed["last_outcome"] == "failed"
    assert failed["last_failure_kind"] == "IntegrityError"
    assert failed["last_report"] is None
    assert "a@b.c" not in str(body)
    assert job(body, "knowledge_reverification")["last_report"] == "Nothing was overdue."


def test_a_failure_kind_is_read_only_from_a_detail_that_starts_with_an_identifier() -> None:
    """Delete this and a detail that is all message is served as though its first words were a
    type name."""
    assert failure_kind("RuntimeError: broke") == "RuntimeError"
    assert failure_kind("psycopg.errors.UniqueViolation: dup") == "psycopg.errors.UniqueViolation"
    assert failure_kind("the key (x)=(y) collided: sorry") is None
    assert failure_kind("no colon at all") is None
    assert failure_kind(None) is None


# ------------------------------------------------------------------------ the controls


def test_pausing_writes_the_row_the_tick_reads_and_the_list_says_who_paused_it(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """The positive case: the feature on, the authority over everything, the job visible.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    client, stub = served
    switched_on(settings)

    answer = post(client, "u_admin", f"{JOBS}/{REFRESH}/pause")

    assert answer.status_code == 200, answer.text
    assert answer.json()["paused"] is True
    assert settings.writes == [
        {
            "key": f"schedule.paused.{REFRESH}",
            "value_type": "boolean",
            "value": True,
            "updated_by": "u_admin",
        }
    ]
    assert stub.commits == 1
    listed = job(get(client, "u_admin", JOBS).json(), REFRESH)
    assert listed["paused"] is True
    assert listed["pause_changed_by"] == "u_admin"


def test_pausing_and_running_now_are_refused_by_name_while_the_feature_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the `schedule_control` switch reaches nothing: the controls work on an
    install that never switched them on."""
    client, stub = served
    for action in ("pause", "run"):
        answer = post(client, "u_admin", f"{JOBS}/{REFRESH}/{action}")
        assert answer.status_code == 404
        assert SWITCHED_OFF in answer.json()["message"]
    assert settings.writes == []
    assert stub.commits == 0


def test_resuming_is_not_behind_the_feature_so_a_switch_turned_off_traps_nothing(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a job paused while the feature was on stays paused with no way back."""
    client, _ = served
    settings.hold(f"schedule.paused.{REFRESH}", True, value_type="boolean", by="u_admin")

    answer = post(client, "u_admin", f"{JOBS}/{REFRESH}/resume")

    assert answer.status_code == 200, answer.text
    assert answer.json()["paused"] is False
    assert settings.rows[f"schedule.paused.{REFRESH}"].value is False


def test_running_now_writes_the_instant_the_request_was_admitted(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and run now writes a request the tick cannot read, or one for the wrong job."""
    client, _ = served
    switched_on(settings)
    before = datetime.now(UTC)

    answer = post(client, "u_admin", f"{JOBS}/{REFRESH}/run")

    assert answer.status_code == 200, answer.text
    written = settings.writes[-1]
    assert written["key"] == f"schedule.run_requested.{REFRESH}"
    assert written["value_type"] == "string"
    at = datetime.fromisoformat(written["value"])
    assert before <= at <= datetime.now(UTC)
    assert job(get(client, "u_admin", JOBS).json(), REFRESH)["run_pending"] is True


def test_a_job_whose_runner_cannot_start_is_refused_with_what_it_needs(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a pause is recorded for a job the worker never starts."""
    client, _ = served
    switched_on(settings)

    answer = post(client, "u_admin", f"{JOBS}/{UNWIRED}/pause")

    assert answer.status_code == 404
    assert "nothing to run yet" in answer.json()["message"]
    assert settings.writes == []


@pytest.mark.parametrize("pid", ["u_none", "u_wide", "u_narrow", "u_elsewhere"])
@pytest.mark.parametrize("action", ["pause", "resume", "run"])
def test_a_caller_who_may_not_control_a_job_is_refused_before_the_database(
    pid: str, action: str
) -> None:
    """No authority, the authority in one department, or the authority without the job's read:
    one refusal, the same with a database and without, and nothing read or written.

    Delete this and a department's administrator pauses the install's retention sweep, or a
    caller who guessed a job's name pauses one they could not have been shown."""
    with console_client(GRANTS, database=False) as (client, _):
        without = post(client, pid, f"{JOBS}/{REFRESH}/{action}")
    with console_client(GRANTS) as (client, stub):
        with_pool = post(client, pid, f"{JOBS}/{REFRESH}/{action}")
        statements = list(stub.statements)

    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert statements == []


def test_a_password_only_sign_in_cannot_pause_a_job(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a stolen password alone stops a guarantee the install depends on."""
    client, _ = served
    switched_on(settings)

    answer = post(client, "u_admin", f"{JOBS}/{REFRESH}/pause", strong=False)

    assert answer.status_code == 404
    assert settings.writes == []


# ------------------------------------------------------------------ one job and its runs


def test_a_jobs_page_shows_its_row_what_stops_without_it_and_its_run_figures(
    served: tuple[TestClient, Stub], runs: Runs, settings: SettingRows
) -> None:
    """The positive case for one job: the list's row read the same way, the registry's sentence
    for what is lost, the counts the database made, and the person who paused it by name.

    Delete this and every refusal below is satisfied by a route that answers nobody."""
    client, _ = served
    runs.figures["started_30d"] = 12
    runs.figures["failed_30d"] = 2
    settings.hold(f"schedule.paused.{REFRESH}", True, value_type="boolean", by="u_admin")

    answer = get(client, "u_wide", f"{JOBS}/{REFRESH}")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["job"]["control"] == REFRESH
    assert body["lost_silently"] == control(REFRESH).lost_silently
    thirty = next(one for one in body["periods"] if one["range"] == "30d")
    assert (thirty["started"], thirty["failed"], thirty["succeeded"]) == (12, 2, 0)
    assert [one["range"] for one in body["periods"]] == [one for one, _ in JOB_PERIODS]
    assert body["job"]["paused"] is True
    assert body["job"]["pause_changed_by"] == "u_admin"
    assert body["people"] == {"u_admin": "Ada Admin"}


def test_a_job_the_reader_may_not_see_is_the_same_404_as_a_name_nothing_registers(
    served: tuple[TestClient, Stub],
) -> None:
    """Both are decided before any statement, so neither the answer nor the database says which.

    Delete this and a caller without the queue's read learns which job names exist by asking."""
    client, stub = served
    hidden = get(client, "u_none", f"{JOBS}/{REFRESH}")
    missing = get(client, "u_wide", f"{JOBS}/no_such_job")
    hidden_runs = get(client, "u_none", f"{JOBS}/{REFRESH}/runs")

    assert hidden.status_code == missing.status_code == hidden_runs.status_code == 404
    assert hidden.json()["message"] == missing.json()["message"] == hidden_runs.json()["message"]
    assert stub.statements == []


def test_a_jobs_history_is_its_runs_newest_first_by_kind_and_report_with_a_cursor(
    served: tuple[TestClient, Stub], runs: Runs
) -> None:
    """A run is shown as the list shows a last run: a failure by its kind and never its message,
    a report whole, a run with no finish as unfinished. Paged by cursor with no count.

    Delete this and the history either leaks a failure's message or cannot be walked."""
    client, _ = served
    start = datetime(2019, 3, 6, 8, tzinfo=UTC)
    runs.past = [
        (uuid.UUID(int=3), start + timedelta(hours=2), None, None, False, None),
        (
            uuid.UUID(int=2),
            start + timedelta(hours=1),
            start + timedelta(hours=1, seconds=2),
            "failed",
            False,
            "IntegrityError: Key (email)=(a@b.c)",
        ),
        (uuid.UUID(int=1), start, start, "ok", False, "Refreshed three reports."),
    ]

    first = get(client, "u_wide", f"{JOBS}/{REFRESH}/runs?limit=2").json()

    assert [one["outcome"] for one in first["items"]] == ["unfinished", "failed"]
    assert first["items"][1]["failure_kind"] == "IntegrityError"
    assert "a@b.c" not in str(first)
    assert first["truncated"] is False
    assert "total" not in first
    rest = get(
        client, "u_wide", f"{JOBS}/{REFRESH}/runs?limit=2&cursor={first['next_cursor']}"
    ).json()
    assert [one["report"] for one in rest["items"]] == ["Refreshed three reports."]
    assert rest["next_cursor"] is None
    failed = get(client, "u_wide", f"{JOBS}/{REFRESH}/runs?filter=outcome:failed").json()
    assert [one["run_id"] for one in failed["items"]] == [str(uuid.UUID(int=2))]


def test_a_history_says_when_its_load_came_back_full(
    served: tuple[TestClient, Stub], runs: Runs
) -> None:
    """Delete this and a job with years of runs reads as one whose history is complete."""
    client, _ = served
    start = datetime(2019, 3, 6, 8, tzinfo=UTC)
    runs.past = [
        (uuid.UUID(int=n + 1), start - timedelta(minutes=n), start, "ok", False, "done")
        for n in range(RUN_HISTORY_LOAD + 1)
    ]
    body = get(client, "u_wide", f"{JOBS}/{REFRESH}/runs").json()
    assert body["truncated"] is True


# ------------------------------------------------------------------ against PostgreSQL


def test_a_jobs_figures_and_history_are_counted_and_read_by_the_database_itself() -> None:
    """`figures_of` counts one job's runs in each window with a filter per figure, and `runs_of`
    reads that job's newest runs and no other job's, run against a real table.

    Delete this and the stub above answers two statements PostgreSQL might refuse or count
    differently: a filtered count is dialect SQL, and a window boundary is the case that is
    always wrong. Dates are 2999 so the windows never cross a real clock."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.jobs_routes import figures_of, run_view, runs_of
    from tests.fixtures.scratch_postgres import engine, modelled, run, sql

    now = datetime(2999, 6, 30, 12, tzinfo=UTC)
    with modelled("brain_jobs_figures", ["ops.control_run"]) as url:
        for days_ago, outcome in ((1, "ok"), (2, "failed"), (10, "refused"), (40, "ok")):
            at = now - timedelta(days=days_ago)
            sql(
                url,
                "INSERT INTO ops.control_run (name, started_at, finished_at, outcome, detail, "
                "report_only) VALUES (%s, %s, %s, %s, %s, false)",
                REFRESH,
                at,
                at + timedelta(seconds=2),
                outcome,
                "IntegrityError: Key (email)=(a@b.c)" if outcome == "failed" else "done",
            )
        sql(
            url,
            "INSERT INTO ops.control_run (name, started_at, report_only) VALUES (%s, %s, false)",
            REFRESH,
            now,
        )
        sql(
            url,
            "INSERT INTO ops.control_run (name, started_at, finished_at, outcome, report_only) "
            "VALUES ('canary_run', %s, %s, 'ok', false)",
            now,
            now,
        )

        async def read() -> tuple[dict[str, int], list[Any]]:
            db = engine(url)
            try:
                async with AsyncSession(db) as session:
                    counted = (await session.execute(figures_of(REFRESH, now))).mappings().one()
                    rows = (await session.execute(runs_of(REFRESH))).all()
                return {str(k): int(v) for k, v in counted.items()}, [one._tuple() for one in rows]
            finally:
                await db.dispose()

        counted, rows = run(read)

    assert (counted["started_7d"], counted["succeeded_7d"], counted["failed_7d"]) == (3, 1, 1)
    assert (counted["started_30d"], counted["reported_only_30d"]) == (4, 1)
    history = [run_view(one) for one in rows]
    assert [one.outcome for one in history] == ["unfinished", "ok", "failed", "refused", "ok"]
    assert history[2].failure_kind == "IntegrityError"
    assert "a@b.c" not in str([one.model_dump() for one in history])
