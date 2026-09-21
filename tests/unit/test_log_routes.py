"""The Logs screen over HTTP: read by the administrator who holds the log over the whole install
under a second factor, refused in one sentence to everybody else, paged without a count, and
searched literally.

Driven through the real application with the table held in memory. The stub answers the one
statement by the columns it selects and records it, so a refusal can be shown to have been made
before any statement was built, and the search can be read off the statement's own parameters.

Task ids: M27.8.14, M27.8.6
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
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.log_routes import LOG_AUTHORITY, MAX_WINDOW
from brain.ops.log_store import ENTRY_COLUMNS, cursor_of, position_of
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.setting_rows import Result, Row

LOGS = f"{API_PREFIX}/logs"
EVERYWHERE = Scope.unrestricted()

#: `u_admin` holds the log and the configuration plane over everything, and `u_prefix` the content
#: plane, which contains it. `u_wide` holds only the existence plane, `u_elsewhere` the log in one
#: department, `u_narrow` the plane and not the log, and `u_none` nothing.
GRANTS = {
    "u_admin": (
        Grant(capability=LOG_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
    ),
    "u_prefix": (
        Grant(capability=LOG_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONTENT), scope=EVERYWHERE),
    ),
    "u_wide": (
        Grant(capability=LOG_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.EXISTENCE), scope=EVERYWHERE),
    ),
    "u_elsewhere": (
        Grant(capability=LOG_AUTHORITY, scope=Scope.department("finance")),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
    ),
    "u_narrow": (Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),),
    "u_none": (),
}

AT = datetime.now(UTC) - timedelta(minutes=5)

#: The end of a window a day longer than a window may be, from the first of January 2019.
TOO_LONG_AFTER = datetime(2019, 1, 1, tzinfo=UTC) + MAX_WINDOW + timedelta(days=1)


def a_row(row_id: int, *, minutes_ago: int = 0) -> Row:
    at = AT - timedelta(minutes=minutes_ago)
    return Row(
        (
            row_id,
            at,
            at,
            "warning",
            "request failed",
            "brain.app:747",
            "3f1c2b0a9d8e4f7a6b5c4d3e2f1a0b9c",
            None,
            4,
            {"outcome": "denied", "detail": "[masked:str/small]"},
        )
    )


class Table:
    """`obs.application_log` in memory: answers the page statement and keeps each one asked."""

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.asked: list[Select[Any]] = []

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        if [one["name"] for one in statement.column_descriptions] != list(ENTRY_COLUMNS):
            return None
        self.asked.append(statement)
        # Every row, and the route's own `limit + 1` decides whether a page is full.
        return Result(self.rows)


@pytest.fixture
def table() -> Table:
    return Table([a_row(100 - n, minutes_ago=n) for n in range(3)])


@pytest.fixture
def served(table: Table) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(table.answer)
        yield client, stub


def test_the_holder_of_the_log_reads_rows_newest_first_with_a_cursor_when_there_is_more(
    served: tuple[TestClient, Stub], table: Table
) -> None:
    """The positive case, for the configuration plane and for the content plane that contains it.

    Delete this and every refusal below is satisfied by a screen nobody can read."""
    client, _ = served
    for pid in ("u_admin", "u_prefix"):
        body = get(client, pid, f"{LOGS}?limit=2").json()

        assert [one["repeats"] for one in body["items"]] == [4, 4]
        assert body["items"][0] == {
            "at": body["items"][0]["at"],
            "last_at": body["items"][0]["last_at"],
            "level": "warning",
            "event": "request failed",
            "origin": "brain.app:747",
            "reference": "3f1c2b0a9d8e4f7a6b5c4d3e2f1a0b9c",
            "error_type": None,
            "repeats": 4,
            "fields": {"outcome": "denied", "detail": "[masked:str/small]"},
        }
        second = table.rows[1]
        assert body["next_cursor"] == cursor_of(second[1], second[0])
        assert "count" not in str(sorted(body))
        assert body["debug_is_not_kept"] is True
        assert body["info_is_a_sample"] is True
        assert body["worker_output_is_not_kept"] is True

    last = get(client, "u_admin", f"{LOGS}?limit=3").json()
    assert len(last["items"]) == 3
    assert last["next_cursor"] is None


@pytest.mark.parametrize("pid", ["u_wide", "u_elsewhere", "u_narrow", "u_none"])
def test_a_reader_without_the_whole_installs_log_is_refused_before_any_statement(
    served: tuple[TestClient, Stub], table: Table, pid: str
) -> None:
    """The existence plane alone, the log held in one department, the plane without the log, and
    nothing: each is the same 404, and no statement was built for any of them.

    Delete this and a department's administrator reads the whole install's log, or a reader told
    the screen exists reads what is on it."""
    client, _ = served
    refused = get(client, pid, LOGS)

    assert refused.status_code == 404
    assert refused.json()["message"] == get(client, "u_none", LOGS).json()["message"]
    assert table.asked == []


def test_the_log_is_refused_to_a_session_without_a_second_factor_even_to_its_holder(
    served: tuple[TestClient, Stub], table: Table
) -> None:
    """`admin:application_log` is withheld by admission from a password-only session.

    Delete this and the capability could be renamed to a `read:` one, and a stolen password would
    read the log."""
    client, _ = served

    assert get(client, "u_admin", LOGS, strong=False).status_code == 404
    assert get(client, "u_admin", LOGS).status_code == 200
    assert len(table.asked) == 1


def test_the_search_is_literal_and_the_level_the_window_and_the_cursor_are_the_ones_asked_for(
    served: tuple[TestClient, Stub], table: Table
) -> None:
    """A search for `50%_off` matches those characters and not a pattern, and each narrowing is
    on the statement.

    Delete this and a search for an underscore matches every event, or a cursor reads the first
    page again."""
    client, _ = served
    start = datetime(2019, 3, 1, tzinfo=UTC)
    end = datetime(2019, 3, 2, tzinfo=UTC)
    cursor = cursor_of(datetime(2019, 3, 1, 12, tzinfo=UTC), 42)
    response = get(
        client,
        "u_admin",
        f"{LOGS}?level=error&event=50%25_off&start={start.isoformat().replace('+', '%2B')}"
        f"&end={end.isoformat().replace('+', '%2B')}&cursor={cursor}",
    )

    assert response.status_code == 200, response.text
    compiled = table.asked[-1].compile()
    params = compiled.params
    assert params["event_1"] == "%50\\%\\_off%"
    assert "ESCAPE '\\'" in str(compiled)
    assert params["level_1"] == "error"
    assert (params["at_1"], params["at_2"]) == (start, end)
    assert (params["param_1"], params["param_2"]) == position_of(cursor)
    assert params["param_3"] == 51
    assert response.json()["start"].startswith("2019-03-01")


def test_oldest_first_walks_the_log_forward_from_its_cursor_and_newest_first_walks_it_back(
    served: tuple[TestClient, Stub], table: Table
) -> None:
    """The order is on the statement, and a cursor continues in the order its page was read in.

    Delete this and oldest first sorts the page in the browser while the statement still reads the
    newest rows, which is the first page of what arrived; or a cursor from an oldest-first page is
    compared backwards and reads the page it came from again."""
    client, _ = served
    cursor = cursor_of(datetime(2019, 3, 1, 12, tzinfo=UTC), 42)

    newest = get(client, "u_admin", f"{LOGS}?cursor={cursor}")
    newest_sql = str(table.asked[-1].compile())
    oldest = get(client, "u_admin", f"{LOGS}?order=oldest&cursor={cursor}")
    oldest_sql = str(table.asked[-1].compile())
    refused = get(client, "u_admin", f"{LOGS}?order=sideways")

    assert newest.status_code == oldest.status_code == 200
    assert "ORDER BY" in newest_sql and "DESC" in newest_sql.split("ORDER BY")[1]
    assert "DESC" not in oldest_sql.split("ORDER BY")[1]
    assert ") < (" in " ".join(newest_sql.split())
    assert ") > (" in " ".join(oldest_sql.split())
    assert refused.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "start=2019-03-01T00:00:00",
        "start=2019-03-02T00:00:00%2B00:00&end=2019-03-01T00:00:00%2B00:00",
        f"start=2019-01-01T00:00:00%2B00:00&end={TOO_LONG_AFTER.isoformat().replace('+', '%2B')}",
        "cursor=not-a-cursor",
        "cursor=12.x",
        "limit=0",
        "level=debug",
    ],
)
def test_a_malformed_window_cursor_limit_or_level_is_refused_with_422(
    served: tuple[TestClient, Stub], table: Table, query: str
) -> None:
    """A naive instant, an inverted or overlong window, a cursor this route did not write, a page
    of nothing, and debug, which is never kept.

    Delete this and a reader can ask for a year of rows at once, or a malformed cursor reads as
    the first page."""
    client, _ = served

    assert get(client, "u_admin", f"{LOGS}?{query}").status_code == 422
    assert table.asked == []


def test_a_cursor_is_the_position_it_was_made_from() -> None:
    """Delete this and paging skips or repeats a row at a microsecond boundary."""
    at = datetime(2019, 3, 6, 9, 0, 0, 123456, tzinfo=UTC)

    assert position_of(cursor_of(at, 7)) == (at, 7)
    with pytest.raises(ValueError):
        position_of("7")
