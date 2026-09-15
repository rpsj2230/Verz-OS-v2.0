"""Who asked, against a real server: the table `0038` builds, and the route writing to it.

Two halves. The table: `0038` is run for real and compared against the model, row-level security
is on, the application role may read and append and do nothing else, and a second record under
one trace is dropped rather than stored. The path: the real application answers questions
through the real route, the question recorder writes them to this database, and adoption is
read back through `adoption_view` and compared with what was asked, including a refused record,
an absent one, a request the gate turned away, a machine and a hop.

Every test here skips without `DATABASE_URL`, and CI always sets it.

Task ids: M37.3.2.4
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.adoption import Asked, DepartmentAdoption
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.adoption_view import adoption_for_reader
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.fast_lane import FastPathRule
from brain.ops.question_store import QuestionRecorder, asked_between, record
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, modelled, run, shape, sql
from tests.unit.test_answer_route import HOURS as PRICE
from tests.unit.test_answer_route import OneRow
from tests.unit.test_api_routes import SOURCE, token_for
from tests.unit.test_request_finish import wired

TABLES = ("ops.question_asked",)
USAGE = Capability(value="read:usage")

#: Far outside any plausible wall clock, for the tests not about the present.
LATER = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)

#: A rule answering with a column one of the test people may not read.
COST = FastPathRule(
    rule_id="price_list_cost",
    template="what is the cost of {sku}",
    slot="sku",
    source=SOURCE,
    entity="price_list",
    match_field="sku",
    answer_field="cost",
)


@contextmanager
def built(database: str) -> Iterator[str]:
    """A fresh database with `0034` onwards run for real. See `test_spend_report_view.built`."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", "0033")
        migrate(database, "upgrade", "0038")
        yield scratch
    finally:
        drop(database)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with built("brain_test_question_store") as url:
        yield url


@pytest.fixture(autouse=True)
def empty(database: str) -> None:
    sql(database, "TRUNCATE ops.question_asked")


def asked(trace: str, pid: str = "u_one", department: str = "web", at: datetime = LATER) -> Asked:
    return Asked(
        trace_id=trace,
        principal_id=pid,
        principal_kind=PrincipalKind.HUMAN,
        channel=Channel.CONSOLE,
        department=department,
        at=at,
    )


def write_as_app(database: str, *questions: Asked) -> list[bool]:
    """Record through `record`, in one session running as the application role, committed."""

    async def go() -> list[bool]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                kept = [await record(session, one) for one in questions]
                await session.commit()
                return kept
        finally:
            await bound.dispose()

    return run(go)


def read_window(database: str, start: datetime, end: datetime) -> tuple[Asked, ...]:
    async def go() -> tuple[Asked, ...]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return await asked_between(session, start=start, end=end)
        finally:
            await bound.dispose()

    return run(go)


# --- the table ------------------------------------------------------------------------------


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it(database: str) -> None:
    """Compared as constraints, indexes and columns read back from two servers' catalogues, one
    built by `0038` and one by the model, so a width, a check or an index that differs fails
    here rather than at the first write in production.

    Delete this and the migration's copy of the channel list can fall behind `Channel`, and the
    first question from a new channel is refused by the database inside the lane's `finally`."""
    with modelled("brain_test_question_store_model", TABLES) as from_model:
        assert shape(database, TABLES) == shape(from_model, TABLES)


def test_the_question_table_has_row_level_security_and_the_app_may_only_read_and_append(
    database: str,
) -> None:
    """Row-level security on, SELECT and INSERT granted to the application role and nothing
    else, and both policies read back from the server rather than from the migration's text.

    Delete this and a later migration can grant UPDATE, and who asked a question becomes an
    edit anybody holding the application's credentials can make."""
    (secured,) = sql(
        database, "SELECT relrowsecurity FROM pg_class WHERE oid = 'ops.question_asked'::regclass"
    )
    granted = {
        one[0]
        for one in sql(
            database,
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'brain_app' AND table_schema = 'ops' "
            "AND table_name = 'question_asked'",
        )
    }
    policies = {
        (one[0], one[1])
        for one in sql(
            database,
            "SELECT polname, polcmd FROM pg_policy WHERE polrelid = 'ops.question_asked'::regclass",
        )
    }

    assert secured == (True,)
    assert granted == {"SELECT", "INSERT"}
    assert policies == {("question_asked_readable", "r"), ("question_asked_appendable", "a")}


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ops.question_asked SET department = 'hr'",
        "DELETE FROM ops.question_asked",
    ],
)
def test_the_application_role_cannot_change_or_remove_a_recorded_question(
    database: str, statement: str
) -> None:
    """Refused by the server, as the role the application connects as. The positive sibling is
    every write below, which runs as the same role.

    Delete this and the grant can widen with the migration test still green, because that test
    reads the grant and this one exercises it."""
    write_as_app(database, asked("t-kept"))
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)

    assert sql(database, "SELECT department FROM ops.question_asked") == [("web",)]


def test_the_first_record_of_a_trace_is_kept_and_a_later_one_is_dropped(database: str) -> None:
    """See `brain.ops.question_store.THE_FIRST_RECORD_OF_A_TRACE_IS_THE_QUESTION`. A second record
    under one trace, from the same person or from somebody else, is not stored and is reported
    as not kept, and the stored row is the first one's.

    Delete this and a delegated question is several rows, or a reused trace id makes the
    adoption report refuse for every reader."""
    kept = write_as_app(
        database,
        asked("t-root", "u_one"),
        asked("t-root", "u_one", at=LATER + timedelta(seconds=1)),
        asked("t-root", "u_two", department="hr"),
        asked("t-other", "u_two", department="hr"),
    )

    assert kept == [True, False, False, True]
    assert sql(
        database, "SELECT trace_id, principal_id, department FROM ops.question_asked ORDER BY 1"
    ) == [("t-other", "u_two", "hr"), ("t-root", "u_one", "web")]


def test_a_window_holds_its_start_and_not_its_end_and_reads_back_through_asked(
    database: str,
) -> None:
    """`[start, end)`, matching `adoption_by_department`, oldest first, each row rebuilt through
    `Asked`'s own checks.

    Delete this and a question at midnight is counted on both days or on neither."""
    write_as_app(
        database,
        asked("t-before", at=LATER - timedelta(microseconds=1)),
        asked("t-start", at=LATER),
        asked("t-inside", at=LATER + timedelta(hours=1)),
        asked("t-end", at=LATER + timedelta(days=1)),
    )

    found = read_window(database, LATER, LATER + timedelta(days=1))

    assert [one.trace_id for one in found] == ["t-start", "t-inside"]
    assert found[0] == asked("t-start", at=LATER)


# --- the path -------------------------------------------------------------------------------


def test_a_process_started_with_a_database_installs_the_question_recorder(database: str) -> None:
    """`lifespan` itself, against a real server: a process with a database finishes requests into
    the question recorder, bound to the pool it built. Migrations are off because this database
    is already at `0038`.

    `test_request_finish` holds `request_recorders_for` to its answer. This holds `lifespan` to
    calling it, which nothing without a server can do: with no database the right answer is
    empty, and so is the answer of a lifespan that forgot.

    Delete this and a deployed process can start with no recorder and an empty adoption table."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    app: FastAPI = create_app(
        Settings(env="development", database_url=database, run_migrations=False)
    )
    with TestClient(app, raise_server_exceptions=False, backend_options=options):
        installed, _ledger = app.state.request_recorders
        assert isinstance(installed, QuestionRecorder)
        assert installed.sessions is app.state.db_sessions


def a_reader(*departments: str) -> EntitlementSet:
    """Somebody holding one usage grant per department named.

    Two grants of one capability are intersected by `EntitlementSet.scope_for`, so a reader
    named with two departments reaches neither. That is the platform's rule and the test below
    asserts it, because it is what proves this view adds no union of its own.
    """
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(Grant(capability=USAGE, scope=Scope.department(one)) for one in departments),
    )


def everybody() -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_admin", grants=(Grant(capability=USAGE, scope=Scope.unrestricted()),)
    )


def client_on(database: str) -> Iterator[TestClient]:
    """The real application, answering through the real route into this database.

    A selector loop on Windows, for the reason `tests.fixtures.scratch_postgres.run` gives:
    psycopg's async driver refuses the proactor loop.
    """
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    bound = engine(database)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    try:
        with TestClient(app, raise_server_exceptions=False, backend_options=options) as client:
            app.state.gate = wired()
            app.state.tools = build_registry(source=SOURCE, records=OneRow())
            app.state.fast_path_rules = (PRICE, COST)
            app.state.request_recorders = (QuestionRecorder(async_sessionmaker(bound)),)
            yield client
    finally:
        run(bound.dispose)


def ask(
    client: TestClient,
    pid: str,
    question: str,
    *,
    sid: bool = True,
    trace: str | None = None,
) -> Response:
    token = token_for(pid, claims=None if sid else {"sid": None})
    headers = {"authorization": f"Bearer {token}"}
    if trace is not None:
        headers["x-trace-id"] = trace
    answered: Response = client.post(
        f"{API_PREFIX}/answer", headers=headers, json={"question": question}
    )
    return answered


def test_questions_asked_through_the_route_are_what_adoption_reads_back(database: str) -> None:
    """**M37.3.2.4 end to end.** Real requests through the real route, recorded by the lane into
    this database, read back and counted under the usage grant.

    What is sent, and what each must become:

    - an answered question from one person, and a question about a column another person may
      not read, and a question no rule matches: three questions, recorded alike;
    - a request with no token and one with an empty question: turned away by the gate, not
      questions, no rows;
    - a question over the API with no session: a machine, one row, counted as nobody;
    - one question finishing twice under one proposed trace id, the second time from somebody
      else: a hop, one row, the first asker's.

    So `web` has four questions from two people, and `hr` has a line of zeros because it is in
    the reader's reach, not because anything happened there.

    Delete this and every half of the path can pass its own test while nothing arrives in the
    table."""
    for client in client_on(database):
        statuses = [
            ask(client, "u_wide", "what is the price of WEB-1001").status_code,
            ask(client, "u_narrow", "what is the cost of WEB-1001").status_code,
            ask(client, "u_wide", "what colour is the sky").status_code,
            client.post(f"{API_PREFIX}/answer", json={"question": "x"}).status_code,
            ask(client, "u_wide", "").status_code,
            ask(client, "u_wide", "what is the price of WEB-1001", sid=False).status_code,
            ask(client, "u_prefix", "what is the price of WEB-1001", trace="hop-root").status_code,
            ask(client, "u_prefix", "what is the price of WEB-1001", trace="hop-root").status_code,
            ask(client, "u_narrow", "what is the price of WEB-1001", trace="hop-root").status_code,
        ]

    assert statuses == [200, 200, 200, 401, 422, 200, 200, 200, 200]
    now = datetime.now(UTC)
    rows = read_window(database, now - timedelta(hours=1), now + timedelta(hours=1))
    assert len(rows) == 5
    assert sum(one.trace_id == "hop-root" for one in rows) == 1
    assert next(one for one in rows if one.trace_id == "hop-root").principal_id == "u_prefix"
    assert [one.channel for one in rows if one.machine] == [Channel.API]
    assert {one.department for one in rows} == {"web"}

    lines = adoption_for_reader(
        rows,
        ("web", "hr"),
        everybody(),
        start=now - timedelta(hours=1),
        end=now + timedelta(hours=1),
        now=now,
    )
    assert lines == (
        DepartmentAdoption(department="hr", questions=0, people=0),
        DepartmentAdoption(department="web", questions=4, people=3),
    )


def test_a_refused_record_and_a_missing_one_leave_rows_that_differ_only_in_trace_and_time(
    database: str,
) -> None:
    """DENIED and ABSENT in the table. The same person asks about a column they may not read and
    about something no rule knows, and the two rows agree on every column except the trace id
    and the instant.

    Delete this and a column can be added to the table that tells a department head which of
    their people's questions were refused."""
    for client in client_on(database):
        ask(client, "u_narrow", "what is the cost of WEB-1001")
        ask(client, "u_narrow", "what colour is the sky")

    rows = sql(
        database,
        "SELECT principal_id, principal_kind, channel, department FROM ops.question_asked",
    )
    assert len(rows) == 2
    assert rows[0] == rows[1] == ("u_narrow", "human", "console", "web")


def test_a_reader_sees_adoption_only_for_the_departments_their_usage_grant_admits(
    database: str,
) -> None:
    """`adoption_for_reader` narrows through `may_read_spend`. A reader holding the usage grant
    over `hr` alone is shown a zero line for `hr` and nothing about `web`; a reader holding it
    over `web` is shown the question; a reader with no usage grant is shown nothing, as an empty
    answer; and a reader holding two department grants is shown what `scope_for` gives them,
    which is their intersection and therefore nothing, rather than a union this view invented.

    Delete this and the adoption report can be read by anybody who can read the table."""
    write_as_app(database, asked("t-web"))
    rows = read_window(database, LATER, LATER + timedelta(days=1))
    window = {"start": LATER, "end": LATER + timedelta(days=1), "now": LATER}
    nothing_held = EntitlementSet(principal_id="u_x", grants=())

    only_hr = adoption_for_reader(rows, ("web", "hr"), a_reader("hr"), **window)
    only_web = adoption_for_reader(rows, ("web", "hr"), a_reader("web"), **window)
    nobody = adoption_for_reader(rows, ("web", "hr"), nothing_held, **window)
    two_grants = adoption_for_reader(rows, ("web", "hr"), a_reader("web", "hr"), **window)
    unrestricted = adoption_for_reader(rows, ("web", "hr"), everybody(), **window)

    assert only_hr == (DepartmentAdoption(department="hr", questions=0, people=0),)
    assert only_web == (DepartmentAdoption(department="web", questions=1, people=1),)
    assert nobody == ()
    assert two_grants == ()
    assert unrestricted == (
        DepartmentAdoption(department="hr", questions=0, people=0),
        DepartmentAdoption(department="web", questions=1, people=1),
    )
