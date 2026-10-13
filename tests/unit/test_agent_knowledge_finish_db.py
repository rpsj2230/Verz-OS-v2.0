"""Retiring a document and fetching a link again from an agent's Knowledge section, for real.

Every test builds a database migrated to head, an agent whose rule draws on the web department, and
presses the product's own routes over HTTP as the application role with chosen grants, as
`tests/unit/test_knowledge_documents_db.py` does for the Knowledge page. What is stood in is the
network and nothing else: a link is answered by a recorded page and a public resolver, and the
address rule, the scan, the parse, the placement and the supersession are the product's own.

The claims are the ones the leaf makes. A link is fetched again only when a person asks, a newer
version replaces the old one for everybody, whoever may retire a document can take it away, and
after that the agent stops drawing on it at once: it leaves the section's list and a text search
finds nothing of it, while the document stays on file with its history.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector.

Task ids: M39.9.1.5, M39.9.1.1
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from brain import knowledge_intake_routes
from brain.agent_knowledge_routes import (
    THE_PAGE_HAS_NOT_CHANGED,
    THERE_IS_NO_ADDRESS_TO_FETCH_AGAIN,
)
from brain.agent_knowledge_routes import router as agent_knowledge_router
from brain.app import Settings, create_app, suspension_store_for
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Grant
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge_lifecycle_routes import router as lifecycle_router
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.web_pages import PRICING_PAGE, PRICING_URL
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_knowledge_documents_db import company
from tests.unit.test_knowledge_intake_routes import Public, Site
from tests.unit.test_knowledge_lifecycle_db import (
    FINANCE_READER,
    LATER,
    PASSAGE_FIELDS,
    V1,
    WEB_ADMIN,
    WEB_READER,
    _in,
    api,
    ledger,
    searched,
    upload,
    without_trace,
)

pytestmark = pytest.mark.needs_db


AGENT = "web_desk"
TAB_READ = (tab(Tab.KNOWLEDGE).read.requires, *(plane_capability(one) for one in Plane))

#: What each person holds. The administrator adds, reads and may open the section; the reader may
#: open the section and read web's documents and nothing more, so can act on nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    WEB_ADMIN: _in("web", KNOWLEDGE_UPLOAD.value, KNOWLEDGE_READ.value, *PASSAGE_FIELDS)
    + tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in TAB_READ),
    WEB_READER: _in("web", KNOWLEDGE_READ.value, *PASSAGE_FIELDS)
    + tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in TAB_READ),
    FINANCE_READER: _in("finance", KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
}

#: The page a link answers with before and after it changed, each with a word nothing else has.
OLD_WORD, NEW_WORD = "TEALPLAN", "TEALMOVED"
CHANGED_PAGE = PRICING_PAGE.replace(OLD_WORD.encode(), NEW_WORD.encode())
ELSEWHERE = "https://www.example.org/services/other"

#: The date a refetched version is next reviewed, far from any wall clock the test might run at.
REVIEW = LATER + timedelta(days=3650)


def an_agent_drawing_on_web(url: str) -> None:
    """The agent the section is read for, written as superuser, whose rule is `department = web`."""
    row = agent_row(AGENT)
    row.scope = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),)).model_dump()
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with Session(engine) as session, session.begin():
            session.add(row)
    finally:
        engine.dispose()


@contextmanager
def served_company(name: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, Site]]:
    """The database, the agent and a recorded site standing where the network would."""
    site = Site({PRICING_URL: PRICING_PAGE, ELSEWHERE: PRICING_PAGE})
    monkeypatch.setattr(knowledge_intake_routes, "make_fetcher", lambda: site)
    monkeypatch.setattr(knowledge_intake_routes, "make_resolver", Public)
    with company(name) as url:
        an_agent_drawing_on_web(url)
        yield url, site


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes as the application role, the section's and the page's."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(lifecycle_router)
            app.include_router(agent_knowledge_router)
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


def section(client: httpx.AsyncClient, who: str) -> Awaitable[httpx.Response]:
    return client.get(api(f"/agents/{AGENT}/knowledge"), headers=headers(who))


def listed(response: httpx.Response) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200, response.text
    return {one["item_id"]: one for one in response.json()["items"]}


async def link_added(client: httpx.AsyncClient, who: str, url: str = PRICING_URL) -> dict[str, Any]:
    added = await client.post(
        api(f"/agents/{AGENT}/knowledge/links"),
        json={"url": url, "kind": "service_package", "level": "department", "department": "web"},
        headers=headers(who),
    )
    assert added.status_code == 201, added.text
    return dict(added.json())


def refetch(client: httpx.AsyncClient, who: str, item_id: str) -> Awaitable[httpx.Response]:
    return client.post(
        api(f"/agents/{AGENT}/knowledge/{item_id}/refetch"),
        json={"review_by": REVIEW.isoformat()},
        headers=headers(who),
    )


def test_a_retired_document_leaves_the_section_and_every_search_at_once_and_stays_on_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Retiring from the agent's page.** Web's administrator adds a file and sees it listed with
    the act offered. A reader who may open the section but not act on it is not offered it, and
    pressing it anyway is answered in the sentence a missing document gets. The administrator
    retires it: it is gone from the section's list, a text search by a web reader finds nothing of
    it, and the row is still on file as archived.

    Delete this and a button on the agent's page can withdraw nothing, or withdraw for somebody who
    may not, or leave a retired document answering from the agent for as long as a cache holds
    it."""
    with served_company("brain_ak_retire", monkeypatch) as (url, _):

        async def before(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            return {
                "item": first["item_id"],
                "admin": listed(await section(client, WEB_ADMIN)),
                "reader": listed(await section(client, WEB_READER)),
            }

        started = pressed(url, before)
        item = started["item"]
        found = searched(url, WEB_READER, "TEALOLD")

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            path = api(f"/agents/{AGENT}/knowledge/{item}/retire")
            return {
                "refused": await client.post(path, headers=headers(WEB_READER)),
                "missing": await client.post(
                    api(f"/agents/{AGENT}/knowledge/upload.nothing_here/retire"),
                    headers=headers(WEB_READER),
                ),
                "retired": await client.post(path, headers=headers(WEB_ADMIN)),
                "after": listed(await section(client, WEB_ADMIN)),
                "again": await client.post(path, headers=headers(WEB_ADMIN)),
            }

        said = pressed(url, presses)
        state = sql(url, "SELECT state FROM know.item WHERE item_id = %s", item)
        chunks = sql(url, "SELECT DISTINCT state FROM know.chunk WHERE document_id = %s", item)
        silent = searched(url, WEB_READER, "TEALOLD")
        entries = ledger(url, "setting:knowledge_item.")

    assert started["admin"][item]["can_retire"] is True
    assert started["reader"][item]["can_retire"] is False
    assert said["refused"].status_code == said["missing"].status_code == 404
    assert without_trace(said["refused"].json()) == without_trace(said["missing"].json())
    assert said["retired"].status_code == 200, said["retired"].text
    assert item not in said["after"]
    assert said["again"].status_code == 404
    assert [row[0] for row in state] == ["archived"]
    assert [row[0] for row in chunks] == ["archived"]
    assert (WEB_ADMIN, "archived") in [(who, one.get("state")) for who, one in entries]
    assert found.records, "the document was not found before it was retired"
    assert not silent.records, "a retired document was still found by a text search"


def test_a_link_is_fetched_again_only_when_a_person_asks_and_the_newer_page_replaces_the_old(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Fetching a link again.** A link added from the section records how it arrived and the
    address, and is listed as a link with the act offered. Nothing fetches it again by itself:
    listing the section three times asks the site for nothing. Asked for, with the page changed, it
    adds a newer version that supersedes the old one, keeps the same address on record, and a text
    search finds the new word and not the old. Asked for again with the page unchanged, it says so
    and adds nothing. A reader who may not act is refused as for a missing document.

    Delete this and a link can be fetched on a timer nobody asked for, or fetched again into a
    duplicate, or by somebody with no right to change the document."""
    with served_company("brain_ak_refetch", monkeypatch) as (url, site):

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            added = await link_added(client, WEB_ADMIN)
            item = added["item_id"]
            for _ in range(3):
                await section(client, WEB_ADMIN)
            asked_by_listing = list(site.asked)
            seen = listed(await section(client, WEB_ADMIN))
            refused = await refetch(client, WEB_READER, item)
            unchanged = await refetch(client, WEB_ADMIN, item)
            site.pages[PRICING_URL] = CHANGED_PAGE
            changed = await refetch(client, WEB_ADMIN, item)
            return {
                "item": item,
                "seen": seen,
                "asked_by_listing": asked_by_listing,
                "refused": refused,
                "unchanged": unchanged,
                "changed": changed,
                "after": listed(await section(client, WEB_ADMIN)),
            }

        said = pressed(url, presses)
        item = said["item"]
        recorded = sql(url, "SELECT arrived_as, source_url FROM know.item WHERE item_id = %s", item)
        found_old = searched(url, WEB_READER, OLD_WORD)
        found_new = searched(url, WEB_READER, NEW_WORD)
        newer_id = said["changed"].json().get("item_id", "")
        newer_row = sql(url, "SELECT state, source_url FROM know.item WHERE item_id = %s", newer_id)
        old_row = sql(url, "SELECT state FROM know.item WHERE item_id = %s", item)
        entries = ledger(url, "setting:knowledge_item.")

    assert said["asked_by_listing"] == [PRICING_URL], "the page was fetched by being listed"
    assert said["seen"][item]["arrived_as"] == "link"
    assert said["seen"][item]["can_refetch"] is True
    assert "source_url" not in str(said["seen"][item]), "the address was sent in a list"
    assert recorded == [("link", PRICING_URL)]
    assert said["refused"].status_code == 404
    assert said["refused"].json()["message"] == "I could not find that."
    assert said["unchanged"].status_code == 422
    assert said["unchanged"].json()["message"] == THE_PAGE_HAS_NOT_CHANGED
    assert said["changed"].status_code == 201, said["changed"].text
    newer = said["changed"].json()
    assert newer["supersedes"] == item and newer["item_id"] != item
    assert set(said["after"]) == {newer["item_id"]}, "the old version still drew on the agent"
    assert said["after"][newer["item_id"]]["arrived_as"] == "link"
    assert [(who, one.get("change")) for who, one in entries].count((WEB_ADMIN, "added")) == 2
    assert (WEB_ADMIN, "replaced") in [(who, one.get("change")) for who, one in entries]
    assert PRICING_URL not in str(entries), "the address reached the ledger"
    assert newer_row == [("published", PRICING_URL)]
    assert old_row == [("superseded",)]
    assert found_new.records and not found_old.records
    assert site.asked == [PRICING_URL] * 3, "a refetch asked the site other than when asked to"


def test_a_file_and_a_document_from_before_the_columns_are_not_offered_a_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**What is never guessed.** A file records `file` and is not offered a refetch, and pressing
    it
    is refused in words that say there is nothing to fetch. A document written before `0220`, which
    holds neither column, is listed as `unknown` and is not offered one either, even when its text
    begins with an address.

    Delete this and a list can call a file a link because its first line is a web address, and offer
    to fetch what was never fetched."""
    with served_company("brain_ak_unknown", monkeypatch) as (url, site):
        sql(
            url,
            "INSERT INTO know.item (item_id, title, owner_id, visibility, department, state, kind) "
            "VALUES ('upload.before_the_columns', 'Before', %s, 'department', 'web', "
            "'published', 'sop')",
            WEB_ADMIN,
        )

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            return {
                "file": first["item_id"],
                "seen": listed(await section(client, WEB_ADMIN)),
                "refused": await refetch(client, WEB_ADMIN, first["item_id"]),
            }

        said = pressed(url, presses)

    assert said["seen"][said["file"]]["arrived_as"] == "file"
    assert said["seen"][said["file"]]["can_refetch"] is False
    assert said["refused"].status_code == 422
    assert said["refused"].json()["message"] == THERE_IS_NO_ADDRESS_TO_FETCH_AGAIN
    assert said["seen"]["upload.before_the_columns"]["arrived_as"] == "unknown"
    assert said["seen"]["upload.before_the_columns"]["can_refetch"] is False
    assert site.asked == []


def test_a_link_recorded_with_a_private_address_is_refused_by_the_address_rule_on_a_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The refetch goes through the checked door.** A link whose recorded address now points
    inside
    the network (the row is written as the superuser, as a hand repair would) is refused by the
    address check when a person asks to fetch it again, in the link door's own words, and adds
    nothing and asks the site for nothing.

    Delete this and a refetch can become a way to reach a private address the door would refuse."""
    with served_company("brain_ak_private", monkeypatch) as (url, site):

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            added = await link_added(client, WEB_ADMIN)
            sql(
                url,
                "UPDATE know.item SET source_url = %s WHERE item_id = %s",
                "https://169.254.169.254/latest/meta-data/",
                added["item_id"],
            )
            return {
                "item": added["item_id"],
                "refused": await refetch(client, WEB_ADMIN, added["item_id"]),
                "after": listed(await section(client, WEB_ADMIN)),
            }

        said = pressed(url, presses)

    assert said["refused"].status_code == 422
    assert "address check" in said["refused"].json()["message"]
    assert set(said["after"]) == {said["item"]}
    assert site.asked == [PRICING_URL]
