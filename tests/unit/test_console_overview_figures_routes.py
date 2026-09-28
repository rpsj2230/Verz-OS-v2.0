"""The landing screen's figure row over HTTP: who may read it, whose requests it counts, and that
cost is named rather than served as nought.

Driven through the real application with signed-in people and a stub where the pool is, and then
the statement itself against a real PostgreSQL, where rows of two people inside and outside the
window prove the WHERE clause rather than a description of it. The database half skips without
`DATABASE_URL`, and CI always sets it.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.console_overview_figures_routes import (
    COST_IS_NOT_RECORDED,
    FIGURES_PATH,
    OverviewFiguresView,
    request_outcomes,
)
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.telemetry import RequestStatus, RequestTelemetry
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.scratch_postgres import engine, run
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_telemetry_store import LATER, a_row, built, write_as_app

FIGURES = f"{API_PREFIX}{FIGURES_PATH}"
EVERYWHERE = Scope.unrestricted()
PLANES = tuple(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane)


def read(key: str) -> Capability:
    return screen(key).read.requires


#: `u_wide` opens the overview and reads the Usage screen over everything, so they are counted
#: everybody's requests. `u_narrow` opens the overview only, so they are counted their own.
#: `u_none` holds nothing, so the figures are not theirs to read.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_wide": (
        *PLANES,
        *(Grant(capability=read(key), scope=EVERYWHERE) for key in ("overview", "usage")),
    ),
    "u_narrow": (*PLANES, Grant(capability=read("overview"), scope=EVERYWHERE)),
    "u_none": (),
}


def is_outcomes(statement: Any) -> bool:
    """Whether a statement is `request_outcomes`': a status and a count, grouped."""
    if not isinstance(statement, Select):
        return False
    return [one["name"] for one in statement.column_descriptions] == ["status", "count"]


class Outcomes:
    """Answers `request_outcomes` with fixed counts, including a status the page never shows."""

    def answer(self, statement: Any) -> Result | None:
        if not is_outcomes(statement):
            return None
        return Result(
            [
                Row((RequestStatus.ANSWERED.value, 41)),
                Row((RequestStatus.NOTHING_RETURNED.value, 6)),
                Row((RequestStatus.FAILED.value, 2)),
            ]
        )


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(Outcomes().answer)
        yield client, stub


def figures_of(client: TestClient, pid: str) -> OverviewFiguresView:
    response = get(client, pid, FIGURES)
    assert response.status_code == 200, response.text
    return OverviewFiguresView.model_validate(response.json())


def outcome_statements(stub: Stub) -> list[Select[Any]]:
    return [one for one in stub.statements if is_outcomes(one)]


def test_a_reader_of_the_usage_screen_is_counted_everybodys_requests_by_how_they_ended(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case: answered and nothing returned are the database's counts, a failed
    request is in neither, and the statement carries no person. Delete this and the figure row
    could draw the wrong status, or everybody's figures could be narrowed to nobody's."""
    client, stub = served
    body = figures_of(client, "u_wide")

    assert (body.basis, body.answered, body.nothing_returned) == (Basis.EVERYONE.value, 41, 6)
    assert body.range == "7d"
    assert body.until - body.since == timedelta(days=7)
    (statement,) = outcome_statements(stub)
    assert "u_wide" not in statement.compile().params.values()


def test_a_reader_without_the_usage_screen_is_counted_their_own_requests_in_the_statement(
    served: tuple[TestClient, Stub],
) -> None:
    """The narrowing: a reader who could not open Usage is told whose figures these are, and
    the statement itself names them, so nobody else's request is counted for them. Delete this
    and a landing screen could show a colleague's activity to anybody who may open it."""
    client, stub = served
    body = figures_of(client, "u_narrow")

    assert body.basis == Basis.OWN.value
    (statement,) = outcome_statements(stub)
    assert "u_narrow" in statement.compile().params.values()


def test_a_reader_who_may_not_open_the_overview_is_refused_before_anything_is_read(
    served: tuple[TestClient, Stub],
) -> None:
    """The refusal, and its order: a 404 with no statement sent. Delete this and a reader with
    no grant could learn how many requests the company made last week."""
    client, stub = served
    response = get(client, "u_none", FIGURES)

    assert response.status_code == 404
    assert outcome_statements(stub) == []


def test_cost_is_named_as_not_recorded_while_nothing_writes_a_requests_cost(
    served: tuple[TestClient, Stub],
) -> None:
    """Cost travels as a sentence and never as a figure. Delete this and a later edit could send
    0.00, which the page would draw as the company having spent nothing."""
    client, _ = served
    body = figures_of(client, "u_wide")

    assert [(one.figure, one.why) for one in body.not_recorded] == [
        (COST_IS_NOT_RECORDED.figure, COST_IS_NOT_RECORDED.why)
    ]
    assert "cost_minor" not in OverviewFiguresView.model_fields


def test_the_day_a_requests_cost_is_recorded_this_route_is_told_to_serve_it() -> None:
    """Pinned against the flag the agent pages read, so the figure row cannot go on saying cost
    is not recorded after something starts recording it. When this fails, serve the cost here at
    `brain.console.workspace.basis_for` and delete this test. Delete it earlier and the sentence
    outlives the fact."""
    assert RUN_SPEND_IS_RECORDED is False


def test_no_field_on_the_answer_is_a_count_of_what_was_withheld() -> None:
    """Read off the model rather than trusted to a reviewer. Delete this and a field named like
    a total could be added beside a figure that was narrowed to the reader."""
    names = set(OverviewFiguresView.model_fields)
    assert names.isdisjoint(NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT)


# --- the statement against a real server ----------------------------------------------------


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with built("brain_test_overview_figures") as url:
        yield url


def telemetry(principal: str, at: datetime, status: RequestStatus, trace: str) -> RequestTelemetry:
    return dataclasses.replace(a_row(trace, at=at, status=status), principal=principal)


def counted(database: str, *, basis: Basis, caller: str) -> dict[str, int]:
    since, until = LATER - timedelta(days=7), LATER

    async def go() -> dict[str, int]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                rows = await session.execute(
                    request_outcomes(since, until, basis=basis, caller_id=caller)
                )
                return {str(status): int(count) for status, count in rows.all()}
        finally:
            await bound.dispose()

    return run(go)


def test_the_statement_counts_the_window_and_on_the_narrower_basis_only_the_caller(
    database: str,
) -> None:
    """Rows of two people, inside and outside the week, read back as the application role.
    Delete this and the WHERE clause is proved only by the words the stub test compiles, never by
    a server honouring them."""
    inside = LATER - timedelta(days=1)
    before = LATER - timedelta(days=8)
    write_as_app(
        database,
        telemetry("u_one", inside, RequestStatus.ANSWERED, "t-a"),
        telemetry("u_one", inside, RequestStatus.ANSWERED, "t-b"),
        telemetry("u_one", inside, RequestStatus.NOTHING_RETURNED, "t-c"),
        telemetry("u_two", inside, RequestStatus.ANSWERED, "t-d"),
        telemetry("u_one", before, RequestStatus.ANSWERED, "t-e"),
    )

    assert counted(database, basis=Basis.EVERYONE, caller="u_one") == {
        RequestStatus.ANSWERED.value: 3,
        RequestStatus.NOTHING_RETURNED.value: 1,
    }
    assert counted(database, basis=Basis.OWN, caller="u_one") == {
        RequestStatus.ANSWERED.value: 2,
        RequestStatus.NOTHING_RETURNED.value: 1,
    }
    assert counted(database, basis=Basis.OWN, caller="u_three") == {}
