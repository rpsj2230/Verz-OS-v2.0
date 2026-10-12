"""An agent's Knowledge section over HTTP: who is answered as a missing agent, what is listed, and
what is never said.

Driven through the real application with signed-in people and a stub where the pool is. The
documents are handed in where the route reads them (`reader_stored_items`), because what makes a
document the reader's is the policy `tests/unit/test_acceptance_workspace.py` runs against
PostgreSQL; what these tests hold is what the route does with the documents it is handed: narrow
them by the agent's rule, list only those the reader may open, name a verifier only where the badge
does, page them and count nothing. The whole path on an install is an acceptance check.

Task ids: M39.9.1.1, M39.9.1.6
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

import brain.agent_knowledge_routes as routes
from brain.agent_knowledge_routes import (
    A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE,
    AgentKnowledgeView,
    router,
)
from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Grant
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.item import KnowledgeState
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.lifecycle import Authority, StoredItem
from brain.knowledge.search import Reach
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row

AGENT = "web_desk"
WIDE_AGENT = "company_desk"
#: Pinned far outside any plausible wall clock, as `tests/unit/test_scope_and_capability.py` does:
#: the route judges "due" against the real clock, so a date that could be near it would be a
#: test that reports a defect on a schedule nobody chose.
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
FAR_AHEAD = datetime(2999, 1, 1, tzinfo=UTC)

TAB_READ = (
    tab(Tab.KNOWLEDGE).read.requires,
    *(plane_capability(one) for one in Plane),
)

GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in TAB_READ),
    "u_narrow": (),
}


def row_scoped_to(agent_id: str, department: str) -> AgentRow:
    row = agent_row(agent_id)
    row.scope = Scope(
        clauses=(Clause(field="department", op=Op.EQ, value=department),)
    ).model_dump()
    return row


ROWS = {AGENT: row_scoped_to(AGENT, "web"), WIDE_AGENT: agent_row(WIDE_AGENT)}


def item(
    item_id: str,
    *,
    department: str = "web",
    added: int = 0,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
    verified: bool = False,
    review_by: datetime | None = None,
    owner: str = "u_steward",
) -> StoredItem:
    return StoredItem(
        item_id=item_id,
        title=f"Title of {item_id}",
        owner_id=owner,
        visibility=KnowledgeVisibility(
            level=Visibility.DEPARTMENT, owner_id=owner, department=department
        ),
        state=state,
        kind=KnowledgeKind.SOP,
        verified_by="u_verifier" if verified else "",
        verified_at=LONG_AGO if verified else None,
        review_by=review_by,
        added_at=LONG_AGO - timedelta(days=added),
    )


class Library:
    """What `reader_stored_items` hands the route: the items, and who may open which."""

    def __init__(self, items: list[StoredItem], *, readable: set[str] | None = None) -> None:
        self.items = items
        self.readable = readable

    async def __call__(
        self, sessions: Any, reach: Any, now: datetime
    ) -> tuple[Authority, tuple[StoredItem, ...], bool]:
        who = reach.principal_id
        reads = Reach(principal_id=who, departments=("web",))
        adds = Reach(principal_id=who, departments=("web",))
        authority = Authority(principal_id=who, reads=reads, adds=adds)
        shown = tuple(
            one
            for one in self.items
            if self.readable is None or one.item_id in self.readable or authority.may_read(one)
        )
        return authority, shown, False


def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    if statement.column_descriptions[0].get("entity") is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    return None


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Stub]]:
    async def no_names(_session: Any, _ids: Any) -> dict[str, str]:
        return {"u_steward": "Sam Steward", "u_verifier": "Vera Verifier"}

    monkeypatch.setattr(routes, "names_of", no_names)
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(answer)
        yield client, stub


def stock(monkeypatch: pytest.MonkeyPatch, items: list[StoredItem]) -> None:
    monkeypatch.setattr(routes, "reader_stored_items", Library(items))


def knowledge(client: TestClient, pid: str, agent_id: str = AGENT, query: str = "") -> Any:
    return get(client, pid, f"{API_PREFIX}/agents/{agent_id}/knowledge{query}")


def test_a_reader_without_the_knowledge_read_is_answered_as_an_agent_that_does_not_exist(
    served: tuple[TestClient, Stub],
) -> None:
    """The Knowledge address is never a way to learn what an agent draws on: without the tab's read
    the answer is the missing agent's, in the same words. Delete this and anybody who can open an
    agent can list the documents behind it."""
    client, _ = served
    refused = knowledge(client, "u_narrow")
    missing = knowledge(client, "u_narrow", "no_such_agent")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]


def test_a_reader_is_listed_the_documents_the_agents_rule_reaches_and_not_the_others(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling of the refusal: the reader is answered, with the web documents the agent's rule
    names and neither a document elsewhere nor a replaced one. Delete this and the section can
    refuse everything, or list every document the reader can open whatever the agent is for."""
    client, _ = served
    stock(
        monkeypatch,
        [
            item("web_one", added=1),
            item("web_two", added=2),
            item("finance_one", department="finance"),
            item("web_replaced", state=KnowledgeState.SUPERSEDED),
        ],
    )
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin").json())
    assert [one.item_id for one in body.items] == ["web_one", "web_two"]
    assert [(one.field, one.value) for one in body.rule] == [("department", "web")]
    assert body.can_add is True


def test_an_agent_without_a_rule_of_its_own_lists_what_the_reader_may_open(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrestricted rule narrows nothing of its own, so the list is the reader's own documents
    and no more. Delete this and an agent with no rule lists nothing, or lists documents the reader
    was never shown."""
    client, _ = served
    monkeypatch.setattr(
        routes,
        "reader_stored_items",
        Library([item("web_one"), item("finance_one", department="x")]),
    )
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin", WIDE_AGENT).json())
    assert {one.item_id for one in body.items} == {"web_one"}


def test_a_document_the_reader_may_only_see_the_record_of_is_not_listed(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lifecycle read admits a record an administrator may see and not open; the section lists
    only what the reader may read, so it never says an agent draws on something they could not
    open. Delete this and an administrator is told of a document they cannot read."""
    client, _ = served

    async def sees_more(
        sessions: Any, reach: Any, now: datetime
    ) -> tuple[Authority, tuple[StoredItem, ...], bool]:
        who = reach.principal_id
        # Reads nothing in web, adds in web: administers it, and may see its record only.
        authority = Authority(
            principal_id=who,
            reads=Reach(principal_id=who, departments=()),
            adds=Reach(principal_id=who, departments=("web",)),
        )
        found = (item("web_one"),)
        assert all(authority.may_see(one) and not authority.may_read(one) for one in found)
        return authority, found, False

    monkeypatch.setattr(routes, "reader_stored_items", sees_more)
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin").json())
    assert body.items == []


def test_the_answer_carries_no_count_of_anything_and_no_field_that_could_hold_one(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """DENIED and ABSENT are one answer: whatever else the reader's library holds, the body names
    no total, no count and no number of hidden documents, and a page that is full says only that
    more follows. Delete this and a total beside the list is 44 facts about what the reader may
    not see."""
    client, _ = served
    stock(
        monkeypatch,
        [item(f"web_{n}", added=n) for n in range(6)] + [item("finance_x", department="f")],
    )
    body = knowledge(client, "u_admin", query="?limit=2").json()
    assert set(body) == set(AgentKnowledgeView.model_fields)
    assert not [name for name in body if "count" in name or "total" in name or "hidden" in name]
    assert len(body["items"]) == 2
    assert body["more"] is True
    last = knowledge(client, "u_admin", query="?limit=2&offset=4").json()
    assert (len(last["items"]), last["more"]) == (2, False)


def test_the_newest_document_is_listed_first(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A person adding a document looks for it at the top. Delete this and the order is whatever the
    store returned, so a document just added is somewhere in the middle."""
    client, _ = served
    stock(monkeypatch, [item("old", added=30), item("new", added=1), item("middle", added=10)])
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin").json())
    assert [one.item_id for one in body.items] == ["new", "middle", "old"]


def test_a_document_is_shown_with_its_badge_its_steward_and_when_it_is_due(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verified, due and unverified each read as the badge reads them, and a steward is named by
    name. Delete this and the list can show a document as verified that is past its review date."""
    client, _ = served
    stock(
        monkeypatch,
        [
            item("fresh", added=1, verified=True, review_by=FAR_AHEAD),
            item("overdue", added=2, verified=True, review_by=LONG_AGO + timedelta(days=1)),
            item("bare", added=3),
        ],
    )
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin").json())
    by_id = {one.item_id: one for one in body.items}
    assert by_id["fresh"].verification == "verified"
    assert (by_id["fresh"].due, by_id["overdue"].due, by_id["bare"].due) == (False, True, False)
    assert by_id["overdue"].verification == "due"
    assert by_id["bare"].verification == "unverified"
    assert by_id["bare"].added_by_name == "Sam Steward"
    assert by_id["bare"].verified_by_name is None


def test_the_section_says_in_words_that_it_keeps_no_documents_of_its_own() -> None:
    """The rule is a sentence in the body, not only a docstring, so the page can draw it. Delete
    this and the claim that an agent holds no private store has nothing to be held to."""
    assert "company's" in A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE
    assert "never a principal" in A_SECTION_LISTS_THE_COMPANYS_DOCUMENTS_AND_KEEPS_NONE


def test_an_agent_whose_rule_reaches_nothing_is_still_answered_with_its_rule_and_an_empty_list(
    served: tuple[TestClient, Stub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The empty state is the answer, not an error and not a refusal: the page can say what the
    section is for. Delete this and an agent that draws on nothing yet is a blank panel or a 404,
    which the Knowledge tab's population by `POPULATED_HERE` cannot allow."""
    client, _ = served
    stock(monkeypatch, [item("finance_one", department="finance")])
    body = AgentKnowledgeView.model_validate(knowledge(client, "u_admin").json())
    assert (body.items, body.more, body.unread) == ([], False, "")
    assert [(one.field, one.value) for one in body.rule] == [("department", "web")]
