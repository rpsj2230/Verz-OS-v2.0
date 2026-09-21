"""Asking for access over HTTP: one constant reply, a request stored only where it could be granted,
and each owner reading only what was addressed to them.

Driven through the real application with the steward lookup and the request table held in memory.
The stub answers the steward's select, records every insert, and answers the owner's list from the
rows it recorded, so which requests were stored is read off the statements the route made.

Task ids: M4.3.4, M2.2.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert
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


class Requests:
    """The steward's grant row and the request table, in memory."""

    def __init__(self, steward: str | None = STEWARD) -> None:
        self.steward = steward
        self.rows: list[dict[str, Any]] = []

    def answer(self, statement: Any) -> Result | None:
        if isinstance(statement, Insert) and statement.table.name == "access_request":
            self.rows.append(dict(statement.compile().params))
            return Result([])
        if isinstance(statement, Select):
            tables = {getattr(one, "name", "") for one in statement.get_final_froms()}
            if "capability_grant" in tables:
                return Result([self.steward] if self.steward else [])
            if "access_request" in tables:
                # The statement's own comparison, applied to the rows, so a list narrowed by
                # anything but equality with the caller is caught here and not only in CI.
                clause = statement.whereclause
                assert clause is not None and clause.left.name == "owner_id"
                return Result(
                    AccessRequestRow(
                        id=None,
                        requested_at=datetime(2999, 1, 1, tzinfo=UTC),
                        **{k: v for k, v in row.items() if k != "requested_at"},
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
