"""Adding to an agent's Knowledge from its page: the Knowledge page's own door, and the answer to
whether the agent draws on what was added.

Driven through the real application with signed-in people, over the harness the upload and link
tests use: the link's transport and resolver are recorded pages, the corpus write is kept rather
than written, and everything else, the placement, the door, the scan, the parse and the refusals,
runs for real, because that is the claim: the door is called and not copied. What is stood in
besides is the read-back of the stored document (`added_item`), which is a database read.

Task ids: M39.9.1.2, M39.9.1.3, M39.9.1.4
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

import brain.agent_knowledge_routes as routes
from brain import knowledge_intake_routes, knowledge_routes
from brain.agent_knowledge_routes import (
    LINK_PATH,
    THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED,
    THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED,
    UPLOAD_PATH,
    KnowledgeAddedView,
    router,
)
from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.item import KnowledgeState
from brain.knowledge.lifecycle import StoredItem
from brain.knowledge.search import KNOWLEDGE_UPLOAD
from brain.knowledge_routes import NAME_HEADER
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import console_client, headers
from tests.fixtures.documents import LINE
from tests.fixtures.setting_rows import Result
from tests.fixtures.web_pages import PRICING_PAGE, PRICING_URL
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_knowledge_intake_routes import Public, Queue, Site
from tests.unit.test_knowledge_routes import GRANTS as DOOR_GRANTS
from tests.unit.test_knowledge_routes import Kept, _grant, registry

WEB_AGENT = "web_desk"
FINANCE_AGENT = "finance_desk"
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list before leaving."]).encode()

TAB_READ = (tab(Tab.KNOWLEDGE).read.requires, *(plane_capability(one) for one in Plane))

GRANTS = {
    **DOOR_GRANTS,
    # Adds anywhere and may open the Knowledge section.
    "u_admin": tuple(_grant(one) for one in (KNOWLEDGE_UPLOAD, *TAB_READ)),
    # Adds anywhere and may not open the section at all.
    "u_narrow": (_grant(KNOWLEDGE_UPLOAD),),
}


def row_scoped_to(agent_id: str, department: str) -> AgentRow:
    row = agent_row(agent_id)
    row.scope = Scope(
        clauses=(Clause(field="department", op=Op.EQ, value=department),)
    ).model_dump()
    return row


ROWS = {
    WEB_AGENT: row_scoped_to(WEB_AGENT, "web"),
    FINANCE_AGENT: row_scoped_to(FINANCE_AGENT, "finance"),
}


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    if statement.column_descriptions[0].get("entity") is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    return registry(statement)


class Served:
    def __init__(self, client: TestClient, kept: Kept, site: Site) -> None:
        self.client = client
        self.kept = kept
        self.site = site


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    kept = Kept()
    site = Site({PRICING_URL: PRICING_PAGE})
    monkeypatch.setattr(knowledge_routes, "ingest_document", kept)
    monkeypatch.setattr(knowledge_intake_routes, "make_fetcher", lambda: site)
    monkeypatch.setattr(knowledge_intake_routes, "make_resolver", Public)
    monkeypatch.setattr(knowledge_intake_routes, "queue_for", lambda request: Queue())

    async def read_back(request: Any, asked: Any, item_id: str) -> StoredItem:
        # The database read of the document just stored, stood in by what the door kept.
        (item,) = [one.item for one in kept.stored if one.item.item_id == item_id]
        return StoredItem(
            item_id=item.item_id,
            title=item.title,
            owner_id=item.owner_id,
            visibility=item.visibility,
            state=KnowledgeState.PUBLISHED,
            kind=item.kind,
        )

    monkeypatch.setattr(routes, "added_item", read_back)
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        yield Served(client, kept, site)


def send_file(
    served: Served, pid: str, agent_id: str, *, department: str = "web", name: str = "Handover.md"
) -> Any:
    return served.client.post(
        f"{API_PREFIX}{UPLOAD_PATH.format(agent_id=agent_id)}",
        content=MARKDOWN,
        headers={**headers(pid), "content-type": "text/markdown", NAME_HEADER: quote(name)},
        params={"kind": "sop", "level": "department", "department": department},
    )


def send_link(served: Served, pid: str, agent_id: str, *, department: str = "web") -> Any:
    return served.client.post(
        f"{API_PREFIX}{LINK_PATH.format(agent_id=agent_id)}",
        json={
            "url": PRICING_URL,
            "kind": "service_package",
            "level": "department",
            "department": department,
        },
        headers=headers(pid),
    )


def test_a_file_added_where_the_agents_rule_reaches_is_added_and_said_to_be_drawn_on(
    served: Served,
) -> None:
    """The door stored the file, and the answer is plan_addition's: reached, in one sentence. Delete
    this and the section can add a file and say nothing about whether the agent will use it, which
    is the person repeating the upload."""
    response = send_file(served, "u_admin", WEB_AGENT)
    assert response.status_code == 201, response.text
    body = KnowledgeAddedView.model_validate(response.json())
    assert (body.route, body.reached, body.said) == (
        "upload",
        True,
        THE_AGENT_DRAWS_ON_WHAT_WAS_ADDED,
    )
    assert (body.blocking, body.can_widen) == ([], False)
    (stored,) = served.kept.stored
    assert stored.item.item_id == body.item_id
    assert stored.item.visibility.department == "web"


def test_a_file_added_outside_the_rule_is_added_and_said_not_to_be_drawn_on_with_the_clause(
    served: Served,
) -> None:
    """Adding is not reaching: the file is the company's document in web, the finance agent does
    not draw on it, the answer names the clause that excludes it and offers the draft. Delete this
    and an item outside the rule is reported as reached, or added to the agent silently."""
    response = send_file(served, "u_admin", FINANCE_AGENT, department="web")
    assert response.status_code == 201, response.text
    body = KnowledgeAddedView.model_validate(response.json())
    assert body.reached is False
    assert body.said == THE_AGENT_DOES_NOT_DRAW_ON_WHAT_WAS_ADDED
    assert [(one.field, one.value) for one in body.blocking] == [("department", "finance")]
    assert body.can_widen is True
    assert len(served.kept.stored) == 1


def test_a_link_is_fetched_once_through_the_checked_door_and_answered_the_same_way(
    served: Served,
) -> None:
    """The page is the door's: fetched once, kept as the company's copy, and the agent's answer is
    the same shape as a file's. Delete this and the link route can bypass the fetch's checks or
    answer in a shape the page does not read."""
    response = send_link(served, "u_admin", WEB_AGENT)
    assert response.status_code == 201, response.text
    body = KnowledgeAddedView.model_validate(response.json())
    assert (body.route, body.reached) == ("link", True)
    assert served.site.asked == [PRICING_URL]
    assert len(served.kept.stored) == 1


def test_a_link_that_leads_inside_the_network_is_refused_in_the_doors_words_and_nothing_is_kept(
    served: Served,
) -> None:
    """The refusal of a private address is the door's, reached through this route: the same code
    and sentence the Knowledge page shows. Delete this and the agent's page is a second, unchecked
    way to make the server read its own network."""
    served.site.pages[PRICING_URL] = "https://169.254.169.254/latest/meta-data/"
    response = send_link(served, "u_admin", WEB_AGENT)
    assert response.status_code == 422
    assert response.json()["problems"][0]["code"] == "not_added"
    assert "refused by the address check" in response.json()["message"]
    assert served.kept.stored == []


@pytest.mark.parametrize("send", [send_file, send_link])
def test_a_reader_without_the_section_is_answered_as_a_missing_agent_before_the_door_runs(
    served: Served, send: Any
) -> None:
    """Without the Knowledge tab's read the answer is the missing agent's 404 and nothing is
    fetched, read or stored, even for a person who may add documents elsewhere. Delete this and the
    agent's address is a way to add documents for somebody who cannot see the agent's page."""
    refused = send(served, "u_narrow", WEB_AGENT)
    missing = send(served, "u_narrow", "no_such_agent")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]
    assert served.kept.stored == []
    assert served.site.asked == []
