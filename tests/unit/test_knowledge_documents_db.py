"""The Knowledge list, a document's history and a verification of several, against a real database.

Every test builds a database migrated to head and presses the routes over HTTP as the application
role, signed in with chosen grants the grant table holds as well, as
`tests/unit/test_knowledge_lifecycle_db.py` does for the single acts. What each proves is one of
the console's Knowledge module claims, where the owner would see it: the list names every version a
reader may open and nothing else, with the steward's name and a review filter; the history says
what happened and when and lists a verification only to whom the badge would name its verifier;
and several documents are verified as several single verifications, each reporting its own outcome.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector.

Task ids: M27.15.40
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from brain.app import Settings, create_app, suspension_store_for
from brain.core.entitlement import Grant
from brain.knowledge.lifecycle import NOT_OFFERED
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge_lifecycle_routes import router as lifecycle_router
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import admin_url, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_knowledge_lifecycle_db import (
    COMPANY,
    FINANCE_READER,
    LATER,
    PASSAGE_FIELDS,
    V1,
    V2,
    WEB_ADMIN,
    WEB_READER,
    _in,
    api,
    file_headers,
    ledger,
    upload,
    verify,
    without_trace,
)

pytestmark = pytest.mark.needs_db

#: Somebody who may add documents in web and read nothing, as an uploader appointed there is.
WEB_UPLOADER = "u_prefix"

GRANTS: dict[str, tuple[Grant, ...]] = {
    WEB_ADMIN: _in("web", KNOWLEDGE_UPLOAD.value, KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    WEB_READER: _in("web", KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    FINANCE_READER: _in("finance", KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    WEB_UPLOADER: _in("web", KNOWLEDGE_UPLOAD.value),
}

#: The display name the web administrator carries, so a row can be told to name and not identify.
ADMIN_NAME = "Aisha Web"

#: A company-wide document placed in finance, which the policy lets every session load and which
#: only somebody reading knowledge, stewarding it or administering finance may see.
FINANCE_POLICY = "upload.finance_policy"


@contextmanager
def company(name: str) -> Iterator[str]:
    """A database at head holding these people, their grants, two departments and one document."""
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
        sql(url, "UPDATE auth.principal SET display_name = %s WHERE id = %s", ADMIN_NAME, WEB_ADMIN)
        sql(
            url,
            "INSERT INTO know.item (item_id, title, owner_id, visibility, department, state, kind, "
            "verified_by, verified_at, review_by) VALUES (%s, %s, %s, 'company', 'finance', "
            "'published', 'policy', %s, now(), %s)",
            FINANCE_POLICY,
            "Expense policy",
            FINANCE_READER,
            FINANCE_READER,
            LATER,
        )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes, the lifecycle's included, as the application role."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(lifecycle_router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.suspensions = suspension_store_for(app.state.db_sessions)
            app.state.console_reads = None
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def rows_of(response: httpx.Response) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200, response.text
    return {one["item_id"]: one for one in response.json()["items"]}


def test_the_list_names_every_version_a_reader_may_open_by_title_and_steward_and_nothing_else() -> (
    None
):
    """**The Knowledge list on a server.** Web's administrator adds a document, verifies it and adds
    a newer version. A web reader's list holds both versions, the older as superseded, each naming
    the steward by their display name; the state and review filters narrow it, and a search finds a
    row by its steward's name. A finance reader's list holds neither, only finance's company-wide
    policy. An uploader who may add in web and read nothing sees web's documents and not finance's
    company-wide one, which the policy loaded for them and `may_see` refused.

    Delete this and the list can name documents the detail route refuses, which tells a reader a
    refusal is a permission, or drop the older versions a history keeps."""
    with company("brain_km_list") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            await verify(client, WEB_ADMIN, first["item_id"])
            second = await client.post(
                api(f"/knowledge/items/{first['item_id']}/versions"),
                params={"review_by": LATER.isoformat()},
                content=V2,
                headers=file_headers(WEB_ADMIN),
            )
            assert second.status_code == 201, second.text

            async def listed(who: str, **params: Any) -> httpx.Response:
                return await client.get(
                    api("/knowledge/documents"), params=params, headers=headers(who)
                )

            return {
                "older": first["item_id"],
                "newer": second.json()["item_id"],
                "reader": await listed(WEB_READER),
                "current": await listed(WEB_READER, filter="state:published"),
                "not_due": await listed(WEB_READER, filter="review:not_due"),
                "due": await listed(WEB_READER, filter="review:due"),
                "by_name": await listed(WEB_READER, q="aisha"),
                "finance": await listed(FINANCE_READER),
                "uploader": await listed(WEB_UPLOADER),
                "unknown_filter": await listed(WEB_READER, filter="owner_id:u_admin"),
            }

        said = pressed(url, presses)

    older, newer = said["older"], said["newer"]
    reader = rows_of(said["reader"])
    assert set(reader) == {older, newer, FINANCE_POLICY}
    assert reader[older]["state"] == "superseded"
    assert reader[newer]["state"] == "published"
    assert reader[newer]["steward_name"] == ADMIN_NAME
    assert reader[newer]["department"] == "web"
    assert "total" not in said["reader"].json() or said["reader"].json()["total"] is None
    assert set(rows_of(said["current"])) == {newer, FINANCE_POLICY}
    assert set(rows_of(said["not_due"])) == {older, newer, FINANCE_POLICY}
    assert rows_of(said["due"]) == {}
    assert set(rows_of(said["by_name"])) == {older, newer}
    assert set(rows_of(said["finance"])) == {FINANCE_POLICY}
    assert set(rows_of(said["uploader"])) == {older, newer}
    assert said["unknown_filter"].status_code == 422


def test_a_document_falls_due_on_the_list_when_its_review_date_has_passed() -> None:
    """The Review due filter reads the date the list sends. A document whose review date has passed
    is on `review:due` and off `review:not_due`, and the row says it is due.

    Delete this and the Review due chip on SCREEN 7 can filter on nothing the row carries."""
    with company("brain_km_due") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            sql(
                url,
                "UPDATE know.item SET review_by = %s WHERE item_id = %s",
                datetime.now(tz=UTC) - timedelta(days=3),
                first["item_id"],
            )
            return {
                "item": first["item_id"],
                "due": await client.get(
                    api("/knowledge/documents"),
                    params={"filter": "review:due"},
                    headers=headers(WEB_READER),
                ),
                "not_due": await client.get(
                    api("/knowledge/documents"),
                    params={"filter": "review:not_due"},
                    headers=headers(WEB_READER),
                ),
            }

        said = pressed(url, presses)

    due = rows_of(said["due"])
    assert set(due) == {said["item"]}
    assert due[said["item"]]["due"] is True
    assert said["item"] not in rows_of(said["not_due"])


def test_a_history_says_what_happened_and_when_and_a_verification_only_to_whom_it_names() -> None:
    """**A document's history from the ledger.** The administrator who verified it reads added,
    verified and replaced; a web reader, who may not be told who verified it, reads added and
    replaced and no verification; no event names anybody; and a finance reader is refused in the
    words an invented id gets.

    Delete this and the history becomes a second way to learn who vouched for a document and when,
    which the badge withholds behind its own capability."""
    with company("brain_km_history") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            await verify(client, WEB_ADMIN, first["item_id"])
            second = await client.post(
                api(f"/knowledge/items/{first['item_id']}/versions"),
                params={"review_by": LATER.isoformat()},
                content=V2,
                headers=file_headers(WEB_ADMIN),
            )
            newer = second.json()["item_id"]

            async def history(who: str, item: str) -> httpx.Response:
                return await client.get(
                    api(f"/knowledge/items/{item}/history"), headers=headers(who)
                )

            return {
                "older": first["item_id"],
                "newer": newer,
                "admin": await history(WEB_ADMIN, newer),
                "reader": await history(WEB_READER, newer),
                "finance": await history(FINANCE_READER, newer),
                "invented": await history(FINANCE_READER, "upload.nothing_here"),
            }

        said = pressed(url, presses)

    def events(response: httpx.Response) -> list[tuple[str, str]]:
        assert response.status_code == 200, response.text
        body = response.json()
        for one in body["events"]:
            assert set(one) == {"item_id", "at", "event"}
        return [(one["item_id"], one["event"]) for one in body["events"]]

    older, newer = said["older"], said["newer"]
    admin = events(said["admin"])
    assert (older, "added") in admin
    assert (older, "verified") in admin
    assert (older, "replaced") in admin
    assert (newer, "added") in admin
    reader = events(said["reader"])
    assert (older, "added") in reader and (older, "replaced") in reader
    assert all(event != "verified" for _, event in reader)
    assert said["finance"].status_code == said["invented"].status_code == 404
    assert without_trace(said["finance"].json()) == without_trace(said["invented"].json())


def test_several_documents_are_verified_as_several_single_verifications() -> None:
    """**Bulk re-verify.** The administrator verifies a live document, an invented id and a replaced
    version at once: the first is verified, and the other two are told the one sentence a document
    they may not act on gets. A web reader asking the same is told that sentence for every one and
    verifies nothing. The ledger holds one verification, by the administrator.

    Delete this and a bulk verify can widen a single act, or say which of the ids exist."""
    with company("brain_km_bulk") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            other = await client.post(
                api("/knowledge/uploads"),
                params={"kind": "sop", "level": "department", "department": "web"},
                content=V2,
                headers=file_headers(WEB_ADMIN),
            )
            second = await client.post(
                api(f"/knowledge/items/{other.json()['item_id']}/versions"),
                params={"review_by": LATER.isoformat()},
                content=V1 + b"\nA third line.",
                headers=file_headers(WEB_ADMIN),
            )
            assert second.status_code == 201, second.text
            asked = [first["item_id"], "upload.nothing_here", other.json()["item_id"]]

            async def several(who: str) -> httpx.Response:
                return await client.post(
                    api("/knowledge/verifications"),
                    json={"item_ids": asked, "review_by": LATER.isoformat()},
                    headers=headers(who),
                )

            return {
                "asked": asked,
                "reader": await several(WEB_READER),
                "admin": await several(WEB_ADMIN),
            }

        said = pressed(url, presses)
        verified = [
            actor
            for actor, details in ledger(url, "setting:knowledge_item.")
            if "verified_at" in str(details.get("changed", ""))
        ]

    live, invented, replaced = said["asked"]
    assert said["admin"].status_code == 200, said["admin"].text
    outcomes = said["admin"].json()["outcomes"]
    admin = [(one["item_id"], one["verified"], one["says"]) for one in outcomes]
    assert admin == [
        (live, True, "verified"),
        (invented, False, NOT_OFFERED),
        (replaced, False, NOT_OFFERED),
    ]
    reader = said["reader"].json()["outcomes"]
    assert [(one["verified"], one["says"]) for one in reader] == [(False, NOT_OFFERED)] * 3
    assert verified == [WEB_ADMIN]
