"""The page a document citation links to, over HTTP: the passages this reader may read, or one 404.

The harness is `tests/unit/test_api_routes.py`'s: the real application, the real token path and
the real `knowledge.read_document` handler from `build_registry`, over a row source that hands back
every passage of every document whatever the statement asked. So anything missing from a page was
removed by the redactor or by the route's own reference check, never left unfetched, and the
refusals below are the walls this route relies on rather than a stand-in's manners.

Task ids: M8.1.2
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.cited_document_routes import CitedDocument
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import KNOWLEDGE_READ
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import SOURCE, token_for, wiring

HANDBOOK = "doc_handbook"
LEDGER = "doc_ledger"

#: Far from any wall clock. A passage's `updated_at` is a stored fact and nothing here ages it.
WRITTEN = datetime(2019, 3, 4, 5, 6, tzinfo=UTC)

#: The ledger's passage first, whose words are a canary, then two of the handbook out of order.
PASSAGES: tuple[dict[str, Any], ...] = (
    {
        "chunk_id": f"{LEDGER}.0001",
        "document_id": LEDGER,
        "ordinal": 1,
        "body": "Invoices above the limit need LEDGERCANARYQUOKKA.",
        "title": "Ledger LEDGERTITLEWOMBAT",
        "section": "Limits",
        "updated_at": WRITTEN,
        "department": "finance",
        "visibility": "department",
        "owner_id": "u_owner",
    },
    {
        "chunk_id": f"{HANDBOOK}.0002",
        "document_id": HANDBOOK,
        "ordinal": 2,
        "body": "Leave is booked a month ahead.",
        "title": "Handbook",
        "section": "Booking",
        "updated_at": WRITTEN,
        "department": "web",
        "visibility": "department",
        "owner_id": "u_owner",
    },
    {
        "chunk_id": f"{HANDBOOK}.0001",
        "document_id": HANDBOOK,
        "ordinal": 1,
        "body": "Annual leave is twenty five days a year.",
        "title": "Handbook",
        "section": "Leave",
        "updated_at": WRITTEN,
        "department": "web",
        "visibility": "department",
        "owner_id": "u_owner",
    },
)

WITHHELD = ("LEDGERCANARYQUOKKA", "LEDGERTITLEWOMBAT", f"{LEDGER}.0001")


def on_the_handbook(capability: str) -> Grant:
    return Grant(
        capability=Capability(value=capability),
        scope=Scope(clauses=(Clause(field="document_id", op=Op.EQ, value=HANDBOOK),)),
    )


#: The plane over everything, and a passage's fields on the handbook only.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_wide": (
        Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope()),
        *(
            on_the_handbook(f"read:knowledge.{field}")
            for field in ("document", "title", "section", "updated_at")
        ),
    ),
    # Every passage field on every document, so the redactor withholds nothing and the route's
    # own reference check is the only thing keeping the ledger off the handbook's page.
    "u_narrow": (
        Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope()),
        *(
            Grant(capability=Capability(value=f"read:knowledge.{field}"), scope=Scope())
            for field in ("document", "title", "section", "updated_at")
        ),
    ),
    "u_none": (),
}


class Store:
    """An `EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


class EveryPassage:
    """A `RowSource` answering the departments query and handing back every passage otherwise."""

    def __init__(self) -> None:
        self.asked: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked.append(query)
        if query.columns == ("slug",):
            return [{"slug": "web"}, {"slug": "finance"}]
        return PASSAGES


@pytest.fixture
def source() -> EveryPassage:
    return EveryPassage()


@pytest.fixture
def client(source: EveryPassage) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = dataclasses.replace(wiring(), store=Store())
        app.state.tools = build_registry(source=SOURCE, records=source)
        yield c


def opened(c: TestClient, document_id: str, pid: str = "u_wide") -> Response:
    got: Response = c.get(
        f"{API_PREFIX}/knowledge/documents/{document_id}",
        headers={"authorization": f"Bearer {token_for(pid)}"},
    )
    return got


def test_a_cited_document_opens_on_its_passages_in_reading_order(client: TestClient) -> None:
    """**The positive case.** The handbook's passages come back in reading order, with their words,
    sections, title and the time the stored copy was written.

    Delete this and a route refusing everything passes every refusal below."""
    got = opened(client, HANDBOOK)

    assert got.status_code == 200
    page = CitedDocument.model_validate(got.json())
    assert page.title == "Handbook"
    assert [one.chunk_id for one in page.passages] == [f"{HANDBOOK}.0001", f"{HANDBOOK}.0002"]
    assert page.passages[0].text == "Annual leave is twenty five days a year."
    assert page.passages[0].section == "Leave"
    assert page.passages[0].updated_at == WRITTEN.isoformat()


def test_a_passage_of_another_document_is_not_on_the_page(client: TestClient) -> None:
    """The source handed back the ledger's passage first, to a reader who may read it; the page is
    the handbook's, so neither the ledger's words nor its title are on it.

    Delete this and the route draws whatever the statement returned under the first title."""
    got = opened(client, HANDBOOK, pid="u_narrow")

    assert got.status_code == 200
    assert CitedDocument.model_validate(got.json()).title == "Handbook"
    for value in WITHHELD:
        assert value not in got.text


def test_a_withheld_document_and_one_that_does_not_exist_are_one_404(client: TestClient) -> None:
    """**DENIED and ABSENT.** The ledger exists and its words are withheld from this reader; a
    reference nothing holds does not exist. Both are the same 404, byte for byte but the trace id.

    Delete this and somebody typing references learns which documents exist."""
    withheld = opened(client, LEDGER)
    absent = opened(client, "doc_nowhere")

    assert withheld.status_code == absent.status_code == 404
    assert {k: v for k, v in withheld.json().items() if k != "trace_id"} == {
        k: v for k, v in absent.json().items() if k != "trace_id"
    }
    for value in WITHHELD:
        assert value not in withheld.text


def test_a_reader_with_no_read_of_the_knowledge_plane_is_answered_as_absent(
    client: TestClient, source: EveryPassage
) -> None:
    """No reach, no statement: the departments are read to find the reach and nothing after it,
    and the answer is the same 404 an absent document gets.

    Delete this and a reader holding nothing is shown the document the source handed back."""
    got = opened(client, HANDBOOK, pid="u_none")
    absent = opened(client, "doc_nowhere")

    assert got.status_code == 404
    assert {k: v for k, v in got.json().items() if k != "trace_id"} == {
        k: v for k, v in absent.json().items() if k != "trace_id"
    }
    assert [one.columns for one in source.asked[:1]] == [("slug",)]


def test_an_unauthenticated_request_is_refused(client: TestClient) -> None:
    """The route takes the dependency every route under the prefix takes.

    Delete this and a document opens for anybody who has its reference."""
    got = client.get(f"{API_PREFIX}/knowledge/documents/{HANDBOOK}")

    assert got.status_code == 401


def test_a_reference_outside_the_grammar_is_refused_before_anything_is_read(
    client: TestClient, source: EveryPassage
) -> None:
    """A reference no item could carry is a 422 from the path's own declaration, identically for
    every such reference, and nothing is read for it.

    Delete this and a reference with a quote in it reaches the handler."""
    got = opened(client, "doc'x")

    assert got.status_code == 422
    assert source.asked == []
