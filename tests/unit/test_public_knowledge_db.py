"""Public knowledge against a real PostgreSQL, through the application's own routes (M10.7.2).

Every test builds a database migrated to head, so `0171`'s columns, role, policies and audit
function are the ones that ship, and presses the routes over HTTP: the Knowledge page's marking
route as signed-in people with chosen grants, and the widget's two routes as a stranger's browser.
What each proves is one clause of the leaf, seen where the owner would see it.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector, which the
chain to head needs; CI has both.

Task ids: M10.7.2
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

import httpx
import psycopg
import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.knowledge.public import OUTSIDE_YOUR_DEPARTMENT, PUBLIC_MARKING
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD, SET_PUBLIC_ROLE
from brain.knowledge_routes import NAME_HEADER
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.documents import LINE
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import admin_url, run, sql
from tests.unit.test_automation_owner_store import app_engine

pytestmark = pytest.mark.needs_db

COMPANY = "c_public_knowledge"
#: The people `tests.unit.test_api_routes` mints tokens for, in the parts this file gives them.
WEB_ADMIN = "u_admin"
FINANCE_ADMIN = "u_elsewhere"
BLIND = "u_wide"
SITE = "https://shop.example.invalid"

PASSAGE_FIELDS: tuple[str, ...] = (
    "read:knowledge.document",
    "read:knowledge.title",
    "read:knowledge.section",
    "read:knowledge.updated_at",
)


def _grants(scope: Scope, *capabilities: str) -> tuple[Grant, ...]:
    return tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities)


WEB = Scope.department("web")
BOTH = Scope(clauses=(Clause(field="department", op=Op.IN, value=("finance", "web")),))

#: Web's administrator adds and decides for web; finance's reads both and decides for finance.
GRANTS: dict[str, tuple[Grant, ...]] = {
    WEB_ADMIN: _grants(
        WEB, KNOWLEDGE_UPLOAD.value, KNOWLEDGE_READ.value, PUBLIC_MARKING.value, *PASSAGE_FIELDS
    ),
    FINANCE_ADMIN: (
        *_grants(BOTH, KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
        *_grants(Scope.department("finance"), PUBLIC_MARKING.value),
    ),
    # Decides for every department and reads nothing.
    BLIND: _grants(Scope.unrestricted(), PUBLIC_MARKING.value),
}

HOURS = LINE.join(["# Opening hours", "", "We open at nine, PUBLICQZHOURS."]).encode()
SALARIES = LINE.join(["# Salary bands", "", "The bands are PRIVATEQZBANDS."]).encode()


@contextmanager
def company(name: str) -> Iterator[str]:
    """A database at head holding two people, their grants and two departments."""
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
    """The application's own routes as the application role, with the widget listing one site."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development", widget_origins=(SITE,)))
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.console_reads = None
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def api(path: str) -> str:
    return f"{API_PREFIX}{path}"


async def upload(client: httpx.AsyncClient, body: bytes, name: str) -> str:
    added = await client.post(
        api("/knowledge/uploads"),
        params={"kind": "sop", "level": "department", "department": "web"},
        content=body,
        headers={
            **headers(WEB_ADMIN),
            "content-type": "text/markdown",
            NAME_HEADER: quote(name),
        },
    )
    assert added.status_code == 201, added.text
    return str(added.json()["item_id"])


async def mark(client: httpx.AsyncClient, who: str, item_id: str, public: bool) -> httpx.Response:
    return await client.put(
        api(f"/knowledge/items/{item_id}/public"), json={"public": public}, headers=headers(who)
    )


async def ask(client: httpx.AsyncClient, session: str, question: str) -> httpx.Response:
    return await client.post(
        api("/widget/questions"),
        json={"session": session, "question": question},
        headers={"Origin": SITE},
    )


def ledger(url: str, item_id: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (row[0], row[1])
        for row in sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE subject = %s ORDER BY seq",
            f"setting:knowledge_item.{item_id}",
        )
    ]


def test_a_department_admin_marks_their_own_document_and_the_ledger_names_them() -> None:
    """**The leaf's audit clause on a server.** Web's administrator marks a web document public
    and then stops it: the row names them while it is public and nobody after, and each press is
    one ledger entry naming them, the columns it changed and which way it went. A second press of
    the same way writes nothing.

    Delete this and a marking could be written with nobody's name on it, or recorded in a way that
    reads the same for publishing a document and withdrawing it."""
    with company("brain_public_marked") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            item = await upload(client, HOURS, "Opening hours.md")
            first = await mark(client, WEB_ADMIN, item, True)
            again = await mark(client, WEB_ADMIN, item, True)
            row = sql(url, "SELECT public_by FROM know.item WHERE item_id = %s", item)
            stopped = await mark(client, WEB_ADMIN, item, False)
            return {"item": item, "first": first, "again": again, "row": row, "stopped": stopped}

        said = pressed(url, presses)
        entries = ledger(url, said["item"])
        after = sql(
            url, "SELECT public_by, public_at FROM know.item WHERE item_id = %s", said["item"]
        )

    assert said["first"].status_code == 200, said["first"].text
    assert said["first"].json()["public"] is True
    assert said["first"].json()["marked_by"] == WEB_ADMIN
    assert said["again"].json()["public"] is True
    assert said["row"] == [(WEB_ADMIN,)]
    assert said["stopped"].json()["public"] is False
    assert after == [(None, None)]
    marks = [(actor, details) for actor, details in entries if "public" in details]
    assert [(actor, details["public"], details["changed"]) for actor, details in marks] == [
        (WEB_ADMIN, True, "public_at,public_by"),
        (WEB_ADMIN, False, "public_at,public_by"),
    ]


def test_another_departments_admin_is_told_they_decide_for_their_own_only() -> None:
    """**The leaf's last clause on a server.** Finance's administrator can read the web document
    and holds the decision for finance: the page shows them no button and the rule's sentence, a
    press is refused in that sentence and changes nothing, and a document that does not exist is
    the 404 a document they may not see would be.

    Delete this and a Department Admin marks every department's knowledge public."""
    with company("brain_public_scoped") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            item = await upload(client, HOURS, "Opening hours.md")
            return {
                "item": item,
                "shown": await client.get(
                    api(f"/knowledge/items/{item}/public"), headers=headers(FINANCE_ADMIN)
                ),
                "pressed": await mark(client, FINANCE_ADMIN, item, True),
                "invented": await mark(client, FINANCE_ADMIN, "upload.nothing_here", True),
                "own": await client.get(
                    api(f"/knowledge/items/{item}/public"), headers=headers(WEB_ADMIN)
                ),
            }

        said = pressed(url, presses)
        row = sql(url, "SELECT public_by FROM know.item WHERE item_id = %s", said["item"])

    shown = said["shown"].json()
    assert (shown["public"], shown["may_change"], shown["says"]) == (
        False,
        False,
        OUTSIDE_YOUR_DEPARTMENT,
    )
    assert said["pressed"].status_code == 422
    assert said["pressed"].json()["message"] == OUTSIDE_YOUR_DEPARTMENT
    assert said["invented"].status_code == 404
    assert row == [(None,)]
    assert said["own"].json()["may_change"] is True


def test_a_visitor_is_answered_from_the_marked_document_and_told_nothing_of_the_other() -> None:
    """**The leaf's first two clauses on a server, through the widget's routes.** Two web
    documents, one marked: a visitor's question finds the marked one's words, and a question about
    the unmarked one is answered with the same status and body as a question about nothing at all.
    Unmarked again, the first is not found either.

    Delete this and the widget can answer from a document nobody marked, or word its not-found by
    what was asked, which tells a stranger which documents exist."""
    with company("brain_public_answered") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            hours = await upload(client, HOURS, "Opening hours.md")
            await upload(client, SALARIES, "Salary bands.md")
            await mark(client, WEB_ADMIN, hours, True)
            minted = await client.post(api("/widget/sessions"), headers={"Origin": SITE})
            session = str(minted.json()["session"])
            found = await ask(client, session, "PUBLICQZHOURS")
            private = await ask(client, session, "PRIVATEQZBANDS")
            nothing = await ask(client, session, "NOTHINGQZATALL")
            await mark(client, WEB_ADMIN, hours, False)
            withdrawn = await ask(client, session, "PUBLICQZHOURS")
            return {
                "hours": hours,
                "found": found,
                "private": private,
                "nothing": nothing,
                "withdrawn": withdrawn,
            }

        said = pressed(url, presses)

    found = said["found"].json()
    assert said["found"].status_code == 200
    assert [one["document_id"] for one in found["passages"]] == [said["hours"]]
    assert "PUBLICQZHOURS" in found["passages"][0]["text"]
    assert (said["private"].status_code, said["private"].json()) == (
        said["nothing"].status_code,
        said["nothing"].json(),
    )
    assert said["private"].json() == {"answer": NOT_FOUND_TEXT, "passages": []}
    assert said["withdrawn"].json() == {"answer": NOT_FOUND_TEXT, "passages": []}


def test_the_public_role_reads_only_the_marked_document_whatever_the_statement_asks() -> None:
    """**The second wall, alone.** As `brain_public`, a statement with no predicate at all returns
    the marked document's passages and item and nothing of the unmarked one, and the item's other
    columns are not the role's to read.

    Delete this and the widget's predicate becomes the only thing standing between a stranger and
    every document, which needs-rupash 26 names as the design that must not ship."""
    with company("brain_public_walled") as url:

        async def presses(client: httpx.AsyncClient) -> tuple[str, str]:
            hours = await upload(client, HOURS, "Opening hours.md")
            salaries = await upload(client, SALARIES, "Salary bands.md")
            await mark(client, WEB_ADMIN, hours, True)
            return hours, salaries

        hours, salaries = pressed(url, presses)
        with psycopg.connect(url) as conn:
            conn.execute(SET_PUBLIC_ROLE)
            chunks = {row[0] for row in conn.execute("SELECT document_id FROM know.chunk")}
            items = {row[0] for row in conn.execute("SELECT item_id FROM know.item")}
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("SELECT owner_id FROM know.item")

    assert chunks == {hours} and items == {hours}
    assert salaries not in chunks


def test_a_document_the_marker_cannot_read_is_absent_to_them_even_where_the_policy_admits_it() -> (
    None
):
    """A company-wide document is admitted by `know.item`'s policy to anybody, so the database
    alone would let somebody who decides for every department and reads nothing mark it. The
    route asks whether they may see it first and answers as it answers an invented id.

    Delete this and a person can put in front of the internet a document they were never allowed
    to read."""
    with company("brain_public_blind") as url:
        sql(
            url,
            "INSERT INTO know.item (item_id, title, owner_id, visibility, state) "
            "VALUES ('upload.company_hours', 'Company hours', %s, 'company', 'published')",
            WEB_ADMIN,
        )

        async def presses(client: httpx.AsyncClient) -> tuple[httpx.Response, httpx.Response]:
            return (
                await mark(client, BLIND, "upload.company_hours", True),
                await mark(client, BLIND, "upload.nothing_here", True),
            )

        blind, invented = pressed(url, presses)
        row = sql(url, "SELECT public_by FROM know.item WHERE item_id = 'upload.company_hours'")

    def said(response: httpx.Response) -> tuple[int, str]:
        return response.status_code, str(response.json()["message"])

    assert said(blind) == said(invented)
    assert blind.status_code == 404
    assert row == [(None,)]
