"""The Incidents screen over HTTP: who may open it, which sources it lists, and what it says each
one blocks.

Driven through the real application with the gate and the in-memory connection records from
`tests/unit/test_connector_routes.py`, so the route is proved as it is served rather than as a
function, and the worker's attempts are `SyncState`s built the way the worker records them.

Task ids: M27.2.7
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import CONNECTORS_READ
from brain.connectors.contract import HealthState
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.incident_routes import (
    INCIDENTS_PATH,
    INCIDENTS_SCREEN,
    NOTHING_HERE_READS_THE_ATTEMPTS,
    WHAT_IT_BLOCKS_IS_NOT_KNOWN,
    IncidentView,
)
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import Connection
from tests.unit.test_connector_routes import (
    LONG_AGO,
    Records,
    SyncRecords,
    a_connection,
    an_attempt,
    attach,
    headers,
)
from tests.unit.test_webhook_routes import NoDatabase, wiring

LISTING: Final = f"{API_PREFIX}{INCIDENTS_PATH}"
WHOLE: Final = Scope.unrestricted()

#: The screen's own read and the plane it asks, which `brain.console.reads.permitted` asks for both.
READS_INCIDENTS: Final = (
    Grant(capability=screen(INCIDENTS_SCREEN).read.requires, scope=WHOLE),
    Grant(capability=plane_capability(Plane.CONFIGURATION), scope=WHOLE),
)

GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_none": (),
    "u_wide": (Grant(capability=Capability(value="read:usage"), scope=WHOLE),),
    "u_narrow": READS_INCIDENTS,
    "u_admin": (
        *READS_INCIDENTS,
        Grant(capability=CONNECTORS_READ, scope=WHOLE),
        Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE),
    ),
}


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring(GRANTS)
        app.state.db_sessions = NoDatabase()
        yield c


def connected(app: FastAPI, *connections: Connection, **attempts: HealthState) -> None:
    """These connections, each with a last attempt that left the health named for it."""
    attach(app, Records(connections), None)
    app.state.connector_sync_records = SyncRecords(
        {name: an_attempt(name, health=health) for name, health in attempts.items()}
    )


def listed(client: TestClient, pid: str = "u_admin") -> dict[str, Any]:
    answer = client.get(LISTING, headers=headers(pid))
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def test_only_a_reader_of_the_screen_may_open_it(app: FastAPI, client: TestClient) -> None:
    """A reader without the screen's read, and one holding some other read, are refused in the
    taxonomy's one sentence; the positive sibling is answered. Delete this and the screen can
    answer anybody signed in, which names every source that is down to everybody."""
    connected(app, a_connection("xero"), xero=HealthState.DOWN)
    for pid in ("u_none", "u_wide"):
        refused = client.get(LISTING, headers=headers(pid))
        assert refused.status_code == 404, pid
        assert refused.json()["message"] == Absent.public_message
    assert listed(client)["items"]


def test_a_source_that_is_down_is_listed_with_every_tool_it_takes_with_it(
    app: FastAPI, client: TestClient
) -> None:
    """**The leaf.** A connected source whose last attempt found it down is listed with that
    state, when the attempt finished, and the tools its own declaration names, in its order.
    Delete this and the screen can list the source with nothing beside it, which is the half of an
    incident nobody can act on."""
    xero = a_connection("xero")
    connected(app, xero, xero=HealthState.DOWN)
    [incident] = listed(client)["items"]
    assert (incident["subject"], incident["state"]) == ("xero", HealthState.DOWN.value)
    assert incident["since"].startswith(LONG_AGO.date().isoformat())
    assert incident["blocks"] == list(manifest_for("xero", xero.settings).tool_names())
    assert incident["blocks_unknown"] == ""


def test_a_degraded_source_is_an_incident_and_a_working_or_unfinished_one_is_not(
    app: FastAPI, client: TestClient
) -> None:
    """Degraded and down are incidents; working is not, and neither is a source nobody finished
    setting up, which goes to whoever connected it. Delete this and the screen is amber for the
    whole of every rollout, or silent about a source that answers slowly."""
    connected(
        app,
        a_connection("xero"),
        a_connection("hubspot"),
        a_connection("freshdesk"),
        xero=HealthState.DEGRADED,
        hubspot=HealthState.OK,
        freshdesk=HealthState.UNCONFIGURED,
    )
    assert [one["subject"] for one in listed(client)["items"]] == ["xero"]


def test_a_source_the_reader_may_not_be_told_of_produces_nothing_at_all(
    app: FastAPI, client: TestClient
) -> None:
    """A reader of the screen who may not be told a source exists is answered as an install where
    nothing is degraded: no row, no tool and no count. Delete this and the blocked list becomes a
    catalogue of operations against sources the reader cannot see."""
    connected(app, a_connection("xero"), xero=HealthState.DOWN)
    body = listed(client, "u_narrow")
    assert body["items"] == []
    assert body["unread"] == ""
    assert "xero" not in str(body)


def test_a_process_with_no_database_says_so_rather_than_listing_nothing(
    client: TestClient,
) -> None:
    """With nothing to read the attempts from, the screen says so in place of the list. Delete
    this and a process that looked at nothing answers that nothing is degraded."""
    body = listed(client)
    assert (body["items"], body["unread"]) == ([], NOTHING_HERE_READS_THE_ATTEMPTS)


def test_a_down_source_this_release_cannot_rebuild_is_listed_with_its_blocks_unknown(
    app: FastAPI, client: TestClient
) -> None:
    """A source whose declaration cannot be rebuilt is still down, and is listed saying what it
    blocks cannot be named. Delete this and the one source nobody can account for disappears from
    the screen exactly when it is down."""
    unreadable = Connection(
        connector="laravel",
        settings={"views": "anything"},
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=LONG_AGO,
    )
    connected(app, unreadable, laravel=HealthState.DOWN)
    [incident] = listed(client)["items"]
    assert (incident["subject"], incident["blocks"]) == ("laravel", [])
    assert incident["blocks_unknown"] == WHAT_IT_BLOCKS_IS_NOT_KNOWN


def test_an_incident_names_what_it_blocks_or_says_why_it_cannot() -> None:
    """Refused at the model: an incident with no blocked tool and no reason, or with both. Delete
    this and a renderer is handed a down source with an empty list beside it."""
    for blocks, unknown in (([], ""), (["xero.list_invoices"], WHAT_IT_BLOCKS_IS_NOT_KNOWN)):
        with pytest.raises(ValidationError):
            IncidentView(
                subject="xero",
                state="down",
                since=LONG_AGO,
                blocks=blocks,
                blocks_unknown=unknown,
            )
