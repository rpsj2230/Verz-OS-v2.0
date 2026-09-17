"""Questions no connected source covers, against a real server: the table `0064` builds, the path.

Three halves. Without a server: which finished requests are gaps, read off the lane's own
abstention. The table: `0064` is run for real and compared against the model, row-level security
is on, the application role may read and append and do nothing else, and a second record under
one trace is dropped. The path: the real application answers questions through the real route,
the gap recorder writes the one kind it records, and the lines are read back through
`brain.console.questions_view`, including an answered question, a refused column, a question no
rule matches and a person with no department, none of which is a gap.

Every test with a database skips without `DATABASE_URL`, and CI always sets it.

Task ids: M27.7.18
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.questions_view import GapLine, gap_lines
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.abstain import Abstention, SearchScope, nothing_connected, nothing_retrieved
from brain.gate.answer import LANE, Answered
from brain.gate.context import Channel
from brain.gate.fast_lane import FastPathRule
from brain.gate.finish import Finished, Origin, ToolCallOutcome
from brain.ops.question_gap_store import (
    Gap,
    GapRecorder,
    QuestionGapError,
    gap_of,
    gaps_between,
    record_gap,
)
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, modelled, run, shape, sql
from tests.unit.test_answer_route import HOURS as PRICE
from tests.unit.test_answer_route import OneRow
from tests.unit.test_api_routes import SOURCE, token_for
from tests.unit.test_question_store import COST
from tests.unit.test_request_finish import wired

TABLES = ("ops.question_gap",)

#: Far outside any plausible wall clock, for the tests not about the present.
LATER = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)

#: The price question's shape, filed under a source this install reads nothing from.
SUPPLIER = FastPathRule(
    rule_id="price_list_supplier",
    template="who supplies {sku}",
    slot="sku",
    source="xero",
    entity="price_list",
    match_field="sku",
    answer_field="supplier",
)


# ----------------------------------------------------------------------- without a server
def finished(outcome: object, *, department: str | None = "web") -> Finished:
    return Finished(
        origin=Origin(
            trace_id="t-gap",
            principal=Principal(
                id="u_asker",
                kind=PrincipalKind.HUMAN,
                employment=Employment.STAFF,
                display_name="Asker",
                primary_department=department,
            ),
            channel=Channel.CONSOLE,
        ),
        at=LATER,
        outcome=outcome,  # type: ignore[arg-type]
        completed_at=LATER,
        entitlement_hash="0" * 32,
        lane=LANE,
        tool_calls=0,
    )


def declined(abstention: Abstention) -> Answered:
    return Answered(frames=("event: done\ndata: \n\n",), abstention=abstention)


def test_a_question_declined_for_a_named_missing_source_is_a_gap() -> None:
    """The positive case: the department from the asker, the source from the abstention.

    Delete this and a recorder that writes nothing passes every refusal below."""
    gap = gap_of(finished(declined(nothing_connected(SearchScope(), missing_source="xero"))))

    assert gap == Gap(trace_id="t-gap", department="web", source="xero", at=LATER)


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        ToolCallOutcome(refused=False),
        declined(nothing_retrieved(SearchScope())),
        declined(nothing_connected(SearchScope())),
    ],
    ids=["fault", "tool_call", "nothing_found", "nothing_connected_with_no_source"],
)
def test_nothing_but_a_named_missing_source_is_a_gap(outcome: object) -> None:
    """A fault, a tool call, a question answered with nothing found and nothing connected at all
    are not gaps. Nothing found is the one that matters: it is also a refusal.

    Delete this and a refusal is counted as a hole in the knowledge base."""
    assert gap_of(finished(outcome)) is None


def test_an_asker_with_no_department_is_counted_nowhere() -> None:
    """For `brain.adoption.question_of`'s reason, a guessed department is worse than none.

    Delete this and a gap is filed under a department nobody asked from."""
    outcome = declined(nothing_connected(SearchScope(), missing_source="xero"))

    assert gap_of(finished(outcome, department=None)) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("trace_id", " "), ("department", ""), ("source", " "), ("at", datetime(2999, 1, 1))],
)
def test_a_gap_with_a_blank_field_or_a_naive_instant_is_refused(field: str, value: object) -> None:
    """Delete this and a row nobody can count or date is written."""
    fields: dict[str, object] = {
        "trace_id": "t",
        "department": "web",
        "source": "xero",
        "at": LATER,
    }
    fields[field] = value
    with pytest.raises(QuestionGapError):
        Gap(**fields)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- against a server
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """A fresh database with `0064` run for real over what `0063` left stamped."""
    scratch = fresh("brain_test_question_gap_store")
    try:
        migrate("brain_test_question_gap_store", "stamp", "0062")
        migrate("brain_test_question_gap_store", "upgrade", "0064")
        yield scratch
    finally:
        drop("brain_test_question_gap_store")


@pytest.fixture(autouse=False)
def empty(database: str) -> None:
    sql(database, "TRUNCATE ops.question_gap")


def a_gap(
    trace: str, *, department: str = "web", source: str = "xero", at: datetime = LATER
) -> Gap:
    return Gap(trace_id=trace, department=department, source=source, at=at)


def write_as_app(database: str, *gaps: Gap) -> list[bool]:
    async def go() -> list[bool]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                kept = [await record_gap(session, one) for one in gaps]
                await session.commit()
                return kept
        finally:
            await bound.dispose()

    return run(go)


def read_window(database: str, start: datetime, end: datetime) -> tuple[Gap, ...]:
    async def go() -> tuple[Gap, ...]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return await gaps_between(session, start=start, end=end)
        finally:
            await bound.dispose()

    return run(go)


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it(database: str) -> None:
    """Constraints, indexes and columns read back from two catalogues, one built by `0064` and
    one by the model.

    Delete this and a width or a check can differ, and the first gap in production is refused
    inside the lane's `finally`."""
    with modelled("brain_test_question_gap_model", TABLES) as from_model:
        assert shape(database, TABLES) == shape(from_model, TABLES)


def test_the_gap_table_has_row_level_security_and_the_app_may_only_read_and_append(
    database: str,
) -> None:
    """Read back from the server rather than from the migration's text.

    Delete this and a later migration can grant UPDATE, and a recorded gap becomes an edit."""
    (secured,) = sql(
        database, "SELECT relrowsecurity FROM pg_class WHERE oid = 'ops.question_gap'::regclass"
    )
    granted = {
        one[0]
        for one in sql(
            database,
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'brain_app' AND table_schema = 'ops' AND table_name = 'question_gap'",
        )
    }
    policies = {
        (one[0], one[1])
        for one in sql(
            database,
            "SELECT polname, polcmd FROM pg_policy WHERE polrelid = 'ops.question_gap'::regclass",
        )
    }

    assert secured == (True,)
    assert granted == {"SELECT", "INSERT"}
    assert policies == {("question_gap_readable", "r"), ("question_gap_appendable", "a")}


@pytest.mark.parametrize(
    "statement", ["UPDATE ops.question_gap SET source = 'hubspot'", "DELETE FROM ops.question_gap"]
)
def test_the_application_role_cannot_change_or_remove_a_recorded_gap(
    database: str, empty: None, statement: str
) -> None:
    """Refused by the server as the application's role; every write here is the positive case.

    Delete this and the grant can widen with the migration test still green."""
    write_as_app(database, a_gap("t-kept"))
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)

    assert sql(database, "SELECT source FROM ops.question_gap") == [("xero",)]


def test_the_first_gap_of_a_trace_is_kept_and_a_window_holds_its_start_and_not_its_end(
    database: str, empty: None
) -> None:
    """One question, one row, and `[start, end)` oldest first through `Gap`'s own checks.

    Delete this and a delegated question is counted twice, or a gap at midnight on both days."""
    kept = write_as_app(
        database,
        a_gap("t-root"),
        a_gap("t-root", source="hubspot"),
        a_gap("t-end", at=LATER + timedelta(hours=1)),
        a_gap("t-start", at=LATER - timedelta(hours=1)),
    )

    assert kept == [True, False, True, True]
    found = read_window(database, LATER - timedelta(hours=1), LATER + timedelta(hours=1))
    assert [one.trace_id for one in found] == ["t-start", "t-root"]
    assert found[1].source == "xero"


def client_on(database: str) -> Iterator[TestClient]:
    """The real application, answering through the real route, recording gaps into this database."""
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
    bound = engine(database)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    try:
        with TestClient(app, raise_server_exceptions=False, backend_options=options) as client:
            app.state.gate = wired()
            app.state.tools = build_registry(source=SOURCE, records=OneRow())
            app.state.fast_path_rules = (PRICE, COST, SUPPLIER)
            app.state.request_recorders = (GapRecorder(async_sessionmaker(bound)),)
            yield client
    finally:
        run(bound.dispose)


def ask(client: TestClient, pid: str, question: str) -> Response:
    answered: Response = client.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for(pid)}"},
        json={"question": question},
    )
    return answered


def test_only_a_question_no_connected_source_covers_is_recorded_and_read_back_as_a_line(
    database: str, empty: None
) -> None:
    """**The leaf end to end.** Real requests through the real route into this database:

    - an answered price question, a cost question from somebody who may not read the cost, and a
      question no rule matches: not gaps, no rows;
    - the supplier question from two people in web and from one with no department: two rows,
      web and xero, and nothing for the person counted nowhere;

    read back and shown to a company-wide reader of both screens as one line.

    Delete this and every half of the path can pass its own test while nothing arrives."""
    for client in client_on(database):
        statuses = [
            ask(client, "u_wide", "what is the price of WEB-1001").status_code,
            ask(client, "u_narrow", "what is the cost of WEB-1001").status_code,
            ask(client, "u_wide", "what colour is the sky").status_code,
            ask(client, "u_wide", "who supplies WEB-1001").status_code,
            ask(client, "u_narrow", "who supplies MNT-2002").status_code,
            ask(client, "u_elsewhere", "who supplies WEB-1001").status_code,
        ]

    assert statuses == [200] * 6
    now = datetime.now(UTC)
    found = read_window(database, now - timedelta(hours=1), now + timedelta(hours=1))
    assert [(one.department, one.source) for one in found] == [("web", "xero"), ("web", "xero")]

    everybody = EntitlementSet(
        principal_id="u_admin",
        grants=(
            Grant(capability=Capability(value="read:question"), scope=Scope.unrestricted()),
            Grant(capability=Capability(value="read:connector"), scope=Scope.unrestricted()),
        ),
    )
    assert gap_lines(found, everybody, now=now) == (
        GapLine(department="web", source="xero", asked=2),
    )
