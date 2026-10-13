"""The System health screen over HTTP: who may open it, what it says of each part, and that it
never turns a part it could not ask into a healthy one.

Driven through the real application with the gate from `tests/unit/test_webhook_routes.py`, so the
route is proved as it is served. This process has no database, no vault and no object store, which
is the case that matters most for a screen about health: every figure says it could not be read.

Task ids: M27.13.2, M27.15.54
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.system_health_routes import (
    BREAKERS_BELONG_TO_THE_MODELS_SCREEN,
    NOTHING_HERE_READS_THE_RUNS,
    OBJECT_STORE_IS_ASKED_AT_START,
    SYSTEM_HEALTH_PATH,
)
from tests.unit.test_connector_routes import headers
from tests.unit.test_webhook_routes import NoDatabase, wiring

URL: Final = f"{API_PREFIX}{SYSTEM_HEALTH_PATH}"
WHOLE: Final = Scope.unrestricted()
IN_WEB: Final = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
READ: Final = screen("incidents").read.requires
PLANE: Final = plane_capability(Plane.CONFIGURATION)

GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_none": (),
    "u_wide": (Grant(capability=READ, scope=WHOLE), Grant(capability=PLANE, scope=WHOLE)),
    "u_narrow": (Grant(capability=READ, scope=IN_WEB), Grant(capability=PLANE, scope=WHOLE)),
}


@pytest.fixture
def app() -> Iterator[FastAPI]:
    yield create_app(Settings(env="development"))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring(GRANTS)
        app.state.db_sessions = NoDatabase()
        app.state.object_store = None
        yield c


def opened(client: TestClient, pid: str = "u_wide") -> dict[str, Any]:
    answer = client.get(URL, headers=headers(pid))
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def test_only_a_reader_of_the_whole_installation_may_open_it_and_every_refusal_is_one_answer(
    client: TestClient,
) -> None:
    """A person with no Incidents screen, and one who holds it over a department, are refused with
    the same status and the same body; the positive sibling is answered. Delete this and the
    vault and the worker are shown to a department's reader, or the refusal says which half of the
    rule failed."""
    refusals = [client.get(URL, headers=headers(pid)) for pid in ("u_none", "u_narrow")]
    assert [one.status_code for one in refusals] == [404, 404]
    # Every field but the request's own trace id, which differs by request.
    assert {k: v for k, v in refusals[0].json().items() if k != "trace_id"} == {
        k: v for k, v in refusals[1].json().items() if k != "trace_id"
    }
    assert refusals[0].json()["message"] == Absent.public_message
    assert opened(client)["parts"]


def test_the_four_headline_parts_are_always_named_and_a_part_nobody_configured_is_said_so(
    client: TestClient,
) -> None:
    """Named rather than left out. Delete this and a part nobody set up reads as a part the screen
    forgot, which are two different people's problems."""
    body = opened(client)
    named = {one["name"]: one for one in body["parts"]}
    assert {"database", "cache", "vault", "sign_in"} <= set(named)
    assert named["vault"]["state"] == "not_configured"
    assert body["vault"]["state"] == "not_configured"


def test_a_process_with_no_database_says_it_cannot_tell_and_holds_no_guarantee(
    client: TestClient,
) -> None:
    """The case a health screen must not get wrong. Delete this and a process that looked at
    nothing shows the worker running and every protection in force."""
    body = opened(client)
    assert body["worker"]["state"] == "unknown"
    assert body["worker"]["last_seen"] is None
    assert body["worker"]["said"] == NOTHING_HERE_READS_THE_RUNS
    assert body["guarantees_said"] == NOTHING_HERE_READS_THE_RUNS
    assert body["guarantees"]
    assert not any(one["held"] for one in body["guarantees"])
    assert all(one["because"] == "not_recorded" for one in body["guarantees"])


def test_object_storage_is_said_to_be_asked_at_start_when_it_is_connected(
    app: FastAPI, client: TestClient
) -> None:
    """Both halves of the object store line. Delete this and a connected store is shown without the
    sentence that nothing asks the bucket now, or an unconnected one without its reason."""
    assert opened(client)["object_store"]["state"] == "unknown"

    class Connected:
        backend = object()
        unconnected = ""

    class NotConnected:
        backend = None
        unconnected = "no object store is configured on this install"

    app.state.object_store = Connected()
    shown = opened(client)["object_store"]
    assert (shown["state"], shown["said"]) == ("ready", OBJECT_STORE_IS_ASKED_AT_START)
    app.state.object_store = NotConnected()
    shown = opened(client)["object_store"]
    assert (shown["state"], shown["said"]) == (
        "not_configured",
        "no object store is configured on this install",
    )


def test_breakers_are_absent_with_a_sentence_for_a_reader_who_may_not_read_the_models_screen(
    client: TestClient,
) -> None:
    """Absent and said, never an empty list. Delete this and a reader who may not see the matrix is
    shown no breakers open, which is a statement nobody measured for them."""
    body = opened(client)
    assert body["breakers"] is None
    assert body["breakers_said"] == BREAKERS_BELONG_TO_THE_MODELS_SCREEN
