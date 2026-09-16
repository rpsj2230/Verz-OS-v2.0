"""The Errors screen over HTTP: failed jobs and failed requests, each shown to the reader the
existing decision admits, and never a message, a person or a count.

Driven through the real application with the run records and the request ledger held in memory.
The stub answers the two statements by the columns they select, and reads the control names the
first statement was bound to, so the property that the bound on the list applies only to jobs the
reader may see is asserted on the statement rather than on the response.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.error_routes import (
    MAX_FAILURES,
    THE_PROCESS_LOG_IS_KEPT_BY_THE_CONTAINER_AND_NOT_BY_THE_APPLICATION,
)
from brain.ops.controls import CONTROLS
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.setting_rows import Result, Row

ERRORS = f"{API_PREFIX}/errors"
EVERYWHERE = Scope.unrestricted()
QUEUE_READ = screen("queue").read.requires
USAGE_READ = screen("service_levels").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)

#: `u_admin` may see failed jobs and the whole install's requests. `u_wide` may see jobs only.
#: `u_elsewhere` holds the usage read in one department, which a request ledger with no
#: department cannot honour. `u_none` holds nothing.
GRANTS = {
    "u_admin": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=USAGE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_wide": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_elsewhere": (
        Grant(capability=QUEUE_READ, scope=EVERYWHERE),
        Grant(capability=USAGE_READ, scope=Scope.department("finance")),
        Grant(capability=CONFIGURATION, scope=EVERYWHERE),
    ),
    "u_none": (),
}

AGO = datetime.now(UTC) - timedelta(hours=1)
LEAKY = "IntegrityError: duplicate key value (email)=(someone@example.invalid)"
REFERENCE = "3f1c2b0a9d8e4f7a6b5c4d3e2f1a0b9c"


class Ledgers:
    """Failed runs and failed requests, and the control names each run query was bound to."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, datetime, datetime | None, str | None]] = [
            ("spend_report_refresh", AGO, AGO, LEAKY)
        ]
        self.requests: list[tuple[str, datetime, str, str, float]] = [
            (REFERENCE, AGO, "model", "failed", 812.0)
        ]
        self.bound: list[list[str]] = []

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        columns = [one["name"] for one in statement.column_descriptions]
        if columns == ["name", "started_at", "finished_at", "detail"]:
            names = next(v for v in statement.compile().params.values() if isinstance(v, list))
            self.bound.append(names)
            return Result(Row(one) for one in self.runs if one[0] in names)
        if columns == ["trace_id", "received_at", "lane", "status", "duration_ms"]:
            return Result(Row(one) for one in self.requests)
        return None


@pytest.fixture
def ledgers() -> Ledgers:
    return Ledgers()


@pytest.fixture
def served(ledgers: Ledgers) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(ledgers.answer)
        yield client, stub


def test_a_reader_of_both_screens_sees_a_failed_job_by_kind_and_a_failed_request_by_reference(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case, and what it leaves out: the exception's message and anything that
    names a person.

    Delete this and every narrowing below is satisfied by a screen that lists nothing."""
    client, _ = served
    body = get(client, "u_admin", ERRORS).json()

    assert body["jobs"] == [
        {
            "control": "spend_report_refresh",
            "started_at": body["jobs"][0]["started_at"],
            "finished_at": body["jobs"][0]["finished_at"],
            "kind": "IntegrityError",
        }
    ]
    assert body["requests"][0]["reference"] == REFERENCE
    assert set(body["requests"][0]) == {"reference", "received_at", "lane", "status", "duration_ms"}
    assert "someone@example.invalid" not in str(body)
    assert body["process_log_is_not_kept"] is True
    assert "standard output" in THE_PROCESS_LOG_IS_KEPT_BY_THE_CONTAINER_AND_NOT_BY_THE_APPLICATION


@pytest.mark.parametrize("pid", ["u_wide", "u_elsewhere", "u_none"])
def test_failed_requests_are_shown_only_to_a_reader_of_the_whole_installs_service_levels(
    served: tuple[TestClient, Stub], pid: str
) -> None:
    """Delete this and a reader who may not see the install's traffic reads when every failed
    question arrived and in which lane."""
    client, _ = served

    assert get(client, pid, ERRORS).json()["requests"] == []


def test_the_run_query_is_bound_to_the_jobs_the_reader_may_see_so_a_full_list_hides_nothing(
    served: tuple[TestClient, Stub], ledgers: Ledgers
) -> None:
    """A reader who may see no job asks for no job's failures, and a reader who may see them all
    asks for all of them.

    Delete this and the bound is applied before the narrowing, so a list that came back full to a
    reader who can see few jobs tells them failures exist that they may not see."""
    client, _ = served
    get(client, "u_none", ERRORS)
    get(client, "u_admin", ERRORS)

    assert ledgers.bound == [[], [one.name for one in CONTROLS]]


def test_a_refused_reader_causes_the_same_statements_as_a_permitted_one(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the time an answer takes tells a reader whether they were refused."""
    client, stub = served
    get(client, "u_none", ERRORS)
    refused = len(stub.statements)
    get(client, "u_admin", ERRORS)

    assert len(stub.statements) - refused == refused == 2


def test_a_list_that_came_back_full_says_so_and_carries_no_figure(
    served: tuple[TestClient, Stub], ledgers: Ledgers
) -> None:
    """Delete this and a truncated list reads as every failure there was."""
    client, _ = served
    ledgers.requests = [(REFERENCE, AGO, "model", "failed", 1.0)] * (MAX_FAILURES + 1)

    body = get(client, "u_admin", ERRORS).json()

    assert len(body["requests"]) == MAX_FAILURES
    assert body["requests_truncated"] is True
    assert body["jobs_truncated"] is False
    assert not {key for key in body if "count" in key or "total" in key}
