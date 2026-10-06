"""A source's steward named on its page, and a steward told of a grant somebody made to themselves.

Against a real PostgreSQL at head, through the application's own routes as the application role,
signed in with chosen grants that the grant table holds as well, for the reason
`tests/unit/test_knowledge_lifecycle_db.py` gives. The connected source is the in-memory `Records`
from `tests/unit/test_connector_routes.py`, since what a connection is has its own tests there;
everything stewardship reads and writes is the database.

What each test proves is M7.7.2 seen where the owner would see it. A source shows its steward, who
until somebody is named is the person who connected it; the source's administrator names somebody
who can reach the source, and a person who cannot, or who is not here, is refused in one sentence;
the ledger records the change. Then a person grants themselves a capability the source declares,
and the source's steward, and nobody else, finds the grant on their list, naming the source and not
the grant's scope. A document's steward is told of a grant reaching their document the same way.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector.

Task ids: M7.7.2
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import quote

import httpx
import psycopg
import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app, suspension_store_for
from brain.connector_routes import (
    ALREADY_STEWARD,
    CONNECTORS_READ,
    SOURCE_PATH,
    STEWARD_PATH,
    STEWARD_REFUSED,
)
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge_routes import NAME_HEADER
from brain.session import make_session_factory
from brain.stewardship_routes import SELF_GRANTS_PATH, TOLD
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.documents import LINE
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import admin_url, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_connector_routes import Records, a_connection

pytestmark = pytest.mark.needs_db

COMPANY: Final = "c_stewardship"

#: Connects the source and uploads documents in web.
ADMIN: Final = "u_admin"
#: Reads what the source declares, so may steward it.
READER: Final = "u_narrow"
#: Reads the connectors screen and nothing the source declares, so may neither steward nor name.
LOOKER: Final = "u_wide"

WHOLE: Final = Scope.unrestricted()
PLANE: Final = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)

#: The field grants a passage is read under, as `test_knowledge_lifecycle_db` grants them.
PASSAGE_FIELDS: Final = (
    "read:knowledge.document",
    "read:knowledge.title",
    "read:knowledge.section",
    "read:knowledge.updated_at",
)


def _in(department: str, *capabilities: str) -> tuple[Grant, ...]:
    return tuple(
        Grant(capability=Capability(value=one), scope=Scope.department(department))
        for one in capabilities
    )


GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    ADMIN: (
        PLANE,
        Grant(capability=CONNECTORS_READ, scope=WHOLE),
        Grant(capability=INSTALL_AUTHORITY, scope=WHOLE),
        *_in("web", KNOWLEDGE_UPLOAD.value, KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    ),
    READER: (PLANE, Grant(capability=Capability(value="read:invoice.*"), scope=WHOLE)),
    LOOKER: (PLANE, Grant(capability=CONNECTORS_READ, scope=WHOLE)),
}

DOCUMENT: Final = LINE.join(["# Site handover", "", "Sign the TEALOLD list."]).encode()


@contextmanager
def company(name: str) -> Iterator[str]:
    """A database at head holding three people, their grants and two departments."""
    if not has_pgvector(admin_url()):
        pytest.skip("the chain to head needs pgvector, which CI's server has")
    with retirable(name) as url:
        for department in ("web", "finance"):
            sql(
                url,
                "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
                "VALUES (%s, %s, %s, %s)",
                COMPANY,
                department,
                department.title(),
                department,
            )
        for person, grants in GRANTS.items():
            a_person(url, person)
            for grant in grants:
                sql(
                    url,
                    "INSERT INTO gate.capability_grant "
                    "(principal_id, capability, scope, granted_by, reason) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    person,
                    grant.capability.value,
                    json.dumps(grant.scope.model_dump(mode="json")),
                    "u_seed",
                    "loaded by the test fixture",
                )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes as the application role, with xero connected by `ADMIN`."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.suspensions = suspension_store_for(app.state.db_sessions)
            app.state.console_reads = None
            app.state.connector_records = Records((a_connection("xero", by=ADMIN),))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def api(path: str) -> str:
    return f"{API_PREFIX}{path.replace('{connector}', 'xero')}"


def granted_to_themselves(url: str, who: str, capability: str, scope: Scope) -> None:
    """`who` granting themselves `capability`, as the application role attributed to them."""
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('brain.actor_id', %s, false)", (who,))
        conn.execute(
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES (%s, %s, %s, %s, 'granted to themselves')",
            (who, capability, json.dumps(scope.model_dump(mode="json")), who),
        )


async def name(client: httpx.AsyncClient, by: str, steward: str) -> httpx.Response:
    return await client.post(api(STEWARD_PATH), json={"steward_id": steward}, headers=headers(by))


async def steward_shown(client: httpx.AsyncClient) -> str:
    shown = await client.get(api(SOURCE_PATH), headers=headers(ADMIN))
    assert shown.status_code == 200, shown.text
    return str(shown.json()["steward"])


async def notices(client: httpx.AsyncClient, who: str) -> dict[str, Any]:
    told = await client.get(api(SELF_GRANTS_PATH), headers=headers(who))
    assert told.status_code == 200, told.text
    return dict(told.json())


def test_a_sources_steward_is_named_by_its_administrator_and_must_be_able_to_reach_it() -> None:
    """**M7.7.2's per-source half on a server.** The source shows the person who connected it as
    its steward; somebody who may not connect it cannot name anybody, and is answered as though
    the source were not there; naming the steward again, a person who reads nothing it declares,
    or a person who is not here is refused in one sentence; naming a reader of its invoices
    succeeds, the page shows them from then on, and the ledger has the change.

    Delete this and a steward can be named who can never act on the source, or by somebody who
    governs nothing, or with nothing in the ledger."""
    with company("brain_m772_steward") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            return {
                "before": await steward_shown(client),
                "by_looker": await name(client, LOOKER, READER),
                "again": await name(client, ADMIN, ADMIN),
                "looker": await name(client, ADMIN, LOOKER),
                "nobody": await name(client, ADMIN, "u_nobody_at_all"),
                "reader": await name(client, ADMIN, READER),
                "after": await steward_shown(client),
            }

        said = pressed(url, presses)
        ledger = sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE subject = 'connector:xero' "
            "ORDER BY seq",
        )

    assert said["before"] == ADMIN
    assert said["by_looker"].status_code == 404
    assert said["again"].status_code == 422
    assert said["again"].json()["problems"][0]["message"] == ALREADY_STEWARD
    for refused in ("looker", "nobody"):
        assert said[refused].status_code == 422, said[refused].text
        assert said[refused].json()["problems"][0]["message"] == STEWARD_REFUSED
    assert said["reader"].status_code == 200, said["reader"].text
    assert (said["reader"].json()["steward_id"], said["reader"].json()["steward_name"]) == (
        READER,
        READER,
    )
    assert said["after"] == READER
    assert ledger == [(ADMIN, {"change": "steward", "steward": READER})]


def test_a_steward_is_told_of_a_grant_somebody_made_to_themselves_and_nobody_else_is() -> None:
    """**The notice, end to end.** After the reader is named the source's steward, the
    administrator grants themselves the source's invoices in one department and the reader grants
    themselves web's knowledge. The reader's list names the administrator's grant and the source
    it reaches, and not the scope; the administrator's list names the reader's grant and the
    document they uploaded; the person who stewards nothing has an empty list, as does everybody
    before either grant.

    Delete this and a self-grant can reach a steward's source or document with nobody told, or
    be told to somebody who answers for none of it."""
    with company("brain_m772_notice") as url:

        async def before(client: httpx.AsyncClient) -> dict[str, Any]:
            named = await name(client, ADMIN, READER)
            assert named.status_code == 200, named.text
            uploaded = await client.post(
                api("/knowledge/uploads"),
                params={"kind": "sop", "level": "department", "department": "web"},
                content=DOCUMENT,
                headers={
                    **headers(ADMIN),
                    "content-type": "text/markdown",
                    NAME_HEADER: quote("Site handover.md"),
                },
            )
            assert uploaded.status_code == 201, uploaded.text
            return {
                "item": uploaded.json()["item_id"],
                "reader": await notices(client, READER),
                "admin": await notices(client, ADMIN),
            }

        first = pressed(url, before)
        granted_to_themselves(url, ADMIN, "read:invoice.*", Scope.department("finance"))
        granted_to_themselves(url, READER, KNOWLEDGE_READ.value, Scope.department("web"))

        async def after(client: httpx.AsyncClient) -> dict[str, Any]:
            return {
                "reader": await notices(client, READER),
                "admin": await notices(client, ADMIN),
                "looker": await notices(client, LOOKER),
            }

        said = pressed(url, after)

    assert first["reader"] == first["admin"] == {"items": [], "told": TOLD}
    [to_reader] = said["reader"]["items"]
    assert (to_reader["person_id"], to_reader["person_name"]) == (ADMIN, ADMIN)
    assert to_reader["capabilities"] == ["read:invoice.*"]
    assert to_reader["reached"] == [{"kind": "source", "object_id": "xero", "label": "Xero"}]
    assert "finance" not in json.dumps(to_reader)
    [to_admin] = said["admin"]["items"]
    assert to_admin["person_id"] == READER
    assert [(one["kind"], one["object_id"]) for one in to_admin["reached"]] == [
        ("document", first["item"])
    ]
    assert said["looker"] == {"items": [], "told": TOLD}
