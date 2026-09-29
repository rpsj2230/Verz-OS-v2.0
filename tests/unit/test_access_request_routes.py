"""Asking for access over HTTP: one constant reply, a request stored only where it could be granted,
and each owner reading only what was addressed to them.

Driven through the real application with the steward lookup and the request table held in memory.
The stub answers the steward's select, records every insert, answers the owner's list from the
rows it recorded and applies the handled mark's update by its own comparisons, so which requests
were stored and marked is read off the statements the route made.

Task ids: M4.3.4, M2.2.4, M27.16.1
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.redaction import ASKER_ACKNOWLEDGEMENT
from brain.core.scope import Scope
from brain.tables.access_request import AccessRequestRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result

REQUESTS = f"{API_PREFIX}/access-requests"
STEWARD = "u_admin"
EVERYWHERE = Scope.unrestricted()


def _grant(capability: str, scope: Scope = EVERYWHERE) -> Grant:
    return Grant(capability=Capability(value=capability), scope=scope)


#: `u_narrow` reaches client rows and names, and the knowledge plane in the web department only.
#: `u_wide` also holds the contract value. `u_none` reaches no client row at all.
GRANTS = {
    "u_narrow": (
        _grant("read:client"),
        _grant("read:client.name"),
        _grant("read:knowledge", Scope.department("web")),
    ),
    "u_wide": (_grant("read:client"), _grant("read:client.contract_value")),
    "u_none": (),
    STEWARD: (),
}


#: The names `auth.principal` holds, which the owner's list carries for its askers.
NAMES = {"u_narrow": "Nadia Narrow", "u_wide": "Wes Wide"}


class Updated:
    """Enough of an update's result for `mark_handled`: how many rows it changed."""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class Requests:
    """The steward's grant row and the request table, in memory."""

    def __init__(self, steward: str | None = STEWARD) -> None:
        self.steward = steward
        self.rows: list[dict[str, Any]] = []

    def answer(self, statement: Any) -> Result | None:
        if isinstance(statement, Insert) and statement.table.name == "access_request":
            self.rows.append({**statement.compile().params, "id": uuid.uuid4(), "handled_at": None})
            return Result([])
        if isinstance(statement, Update) and statement.table.name == "access_request":
            # The update's own three comparisons: this id, this owner, and not handled yet.
            params = statement.compile().params
            found = [
                row
                for row in self.rows
                if row["id"] == params["id_1"]
                and row["owner_id"] == params["owner_id_1"]
                and row["handled_at"] is None
            ]
            for row in found:
                row["handled_at"], row["handled_by"] = params["handled_at"], params["handled_by"]
            return Updated(len(found))
        if isinstance(statement, Select):
            tables = {getattr(one, "name", "") for one in statement.get_final_froms()}
            if "capability_grant" in tables:
                return Result([self.steward] if self.steward else [])
            if "principal" in tables:
                return Result(list(NAMES.items()))
            if "access_request" in tables:
                # The statement's own comparison, applied to the rows, so a list narrowed by
                # anything but equality with the caller is caught here and not only in CI.
                clause = statement.whereclause
                assert clause is not None and clause.left.name == "owner_id"
                return Result(
                    AccessRequestRow(
                        requested_at=datetime(2999, 1, 1, tzinfo=UTC),
                        **{k: v for k, v in row.items() if k not in ("requested_at", "handled_by")},
                    )
                    for row in self.rows
                    if clause.operator(row["owner_id"], clause.right.value)
                )
        return None


@pytest.fixture
def table() -> Requests:
    return Requests()


@pytest.fixture
def served(table: Requests) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(table.answer)
        yield client, stub


def _ask(client: TestClient, pid: str, **body: str) -> dict[str, Any]:
    answered = post(client, pid, REQUESTS, {"question": "why is this hidden from me", **body})
    assert answered.status_code == 202, answered.text
    reply: dict[str, Any] = answered.json()
    return reply


def test_a_locked_field_is_passed_to_the_steward_with_the_askers_question(
    served: tuple[TestClient, Stub], table: Requests
) -> None:
    """The positive case: a reader of client rows without the contract value asks for it, and one
    request is stored, addressed to the steward, naming the capability that would answer it.

    Delete this and every refusal below is satisfied by a route that stores nothing."""
    client, _ = served
    reply = _ask(client, "u_narrow", entity="client", field="contract_value")
    assert reply == {"message": ASKER_ACKNOWLEDGEMENT}
    (row,) = table.rows
    assert (row["owner_id"], row["asker_id"]) == (STEWARD, "u_narrow")
    assert row["requested_capability"] == "read:client.contract_value"
    assert row["question"] == "why is this hidden from me"


@pytest.mark.parametrize(
    ("pid", "body"),
    [
        # Already holds the field: there is no lock, so nothing to ask for.
        ("u_wide", {"entity": "client", "field": "contract_value"}),
        # Reaches no client row: no lock was ever shown to them.
        ("u_none", {"entity": "client", "field": "contract_value"}),
        # An entity nothing classifies, and a field no rule names.
        ("u_narrow", {"entity": "ledger", "field": "balance"}),
        ("u_narrow", {"entity": "client", "field": "shoe_size"}),
        # A department the reader's own scope already admits.
        ("u_narrow", {"department": "web"}),
    ],
)
def test_a_request_that_could_not_be_granted_stores_nothing_and_is_told_the_same(
    served: tuple[TestClient, Stub], table: Requests, pid: str, body: dict[str, str]
) -> None:
    """M4.3.4: the asker learns nothing. The reply is the one constant whether or not a request
    was stored, so a person cannot map fields, owners or departments by asking.

    Delete this and the reply, or its absence of a row, becomes an oracle."""
    client, _ = served
    assert _ask(client, pid, **body) == {"message": ASKER_ACKNOWLEDGEMENT}
    assert table.rows == []


def test_a_department_out_of_reach_is_requested_whether_or_not_it_exists(
    served: tuple[TestClient, Stub], table: Requests
) -> None:
    """M2.2.4's offer: a department the reader's scope does not admit is passed on, decided from
    their own scope and never from the registry, so an invented name is passed on too."""
    client, _ = served
    _ask(client, "u_narrow", department="finance")
    _ask(client, "u_narrow", department="zebra")
    assert [row["department"] for row in table.rows] == ["finance", "zebra"]
    assert {row["requested_capability"] for row in table.rows} == {"read:knowledge"}


def test_an_install_with_no_steward_stores_nothing_and_says_the_same(
    served: tuple[TestClient, Stub], table: Requests
) -> None:
    client, _ = served
    table.steward = None
    assert _ask(client, "u_narrow", entity="client", field="contract_value") == {
        "message": ASKER_ACKNOWLEDGEMENT
    }
    assert table.rows == []


def test_a_body_naming_both_subjects_or_neither_is_refused_by_its_shape(
    served: tuple[TestClient, Stub],
) -> None:
    """The one thing the asker is told about: their own typing."""
    client, _ = served
    both = {"question": "q", "entity": "client", "field": "name", "department": "web"}
    assert post(client, "u_narrow", REQUESTS, both).status_code == 422
    assert post(client, "u_narrow", REQUESTS, {"question": "q"}).status_code == 422


def test_the_owner_reads_the_requests_addressed_to_them_and_nobody_else_does(
    served: tuple[TestClient, Stub],
) -> None:
    """Delivery: the steward's list carries the request with the question in the asker's words;
    the asker's own list, and anybody else's, is empty.

    Delete this and a request is stored where nobody who can grant it ever sees it."""
    client, _ = served
    _ask(client, "u_narrow", entity="client", field="contract_value")
    listed = get(client, STEWARD, REQUESTS).json()
    (item,) = listed["items"]
    assert item["subject"] == "client.contract_value"
    assert item["asker_id"] == "u_narrow"
    assert item["question"] == "why is this hidden from me"
    assert get(client, "u_narrow", REQUESTS).json()["items"] == []
    assert get(client, "u_wide", REQUESTS).json()["items"] == []


def test_the_owner_marks_a_request_handled_once_and_nobody_else_may(
    served: tuple[TestClient, Stub], table: Requests
) -> None:
    """Needs-rupash gap (a): a steward says they dealt with a request, and the list says so. Delete
    this and the mark can be put on by somebody the request was not addressed to, put on twice, or
    answered differently for a request that is not theirs and one that does not exist, which makes
    the route a way of asking which requests exist."""
    client, _ = served
    _ask(client, "u_narrow", entity="client", field="contract_value")
    (row,) = table.rows
    handled = f"{REQUESTS}/{row['id']}/handled"

    by_asker = post(client, "u_narrow", handled, {})
    by_owner = post(client, STEWARD, handled, {})
    again = post(client, STEWARD, handled, {})
    missing = post(client, STEWARD, f"{REQUESTS}/{uuid.uuid4()}/handled", {})
    listed = get(client, STEWARD, f"{REQUESTS}?filter=state:handled").json()

    assert by_owner.status_code == 200, by_owner.text
    assert by_owner.json()["request_id"] == str(row["id"])
    assert row["handled_by"] == STEWARD
    assert by_asker.status_code == again.status_code == missing.status_code == 404
    assert by_asker.json()["message"] == missing.json()["message"]
    (item,) = listed["items"]
    assert item["handled_at"] is not None


def test_the_owners_list_names_who_asked_and_nobody_else(
    served: tuple[TestClient, Stub],
) -> None:
    """The owner reads who asked rather than an id. Delete this and the names can be missing, or
    carry people who asked nothing of this owner."""
    client, _ = served
    _ask(client, "u_narrow", entity="client", field="contract_value")
    listed = get(client, STEWARD, REQUESTS).json()

    assert listed["people"] == {"u_narrow": "Nadia Narrow"}
    assert get(client, "u_wide", REQUESTS).json()["people"] == {}
