"""The answer names the retrieval it was drawn from, a followed citation's place is kept, and the
signal is read by a knowledge administrator alone (M15.3.4).

The real application from `tests/unit/test_answer_route_model.py`, with a passage search that notes
its search as the registered one does, and a retrieval log held in memory in the store's own
shape. What is asserted is the route's part: the header, the one 404 for a use that names nothing,
and who may read the signal. The store over PostgreSQL is the install check's to prove.

Task ids: M15.3.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import RETRIEVAL_HEADER
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.knowledge.document_tools import KnowledgePassage
from brain.knowledge.quality import MINIMUM_EVENTS_FOR_A_SIGNAL, RetrievalEvent
from brain.knowledge.retrieval_log import Searched, note
from brain.knowledge.search import LEXICAL_RETRIEVER
from brain.ops.retrieval_store import StoredRetrievals
from brain.retrieval_routes import NOT_ENOUGH_YET
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_answer_route_model import READER, READER_GRANTS
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_model_lane import VISIBLE, Passages

QUESTION = "how much annual leave do we get"

#: Somebody who runs the knowledge layer, and nothing else.
LIBRARIAN = "u_elsewhere"


class Noting(Passages):
    """The passage stand-in, noting its search as `brain.knowledge.document_tools.searcher` does."""

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        note(
            Searched(
                retrievers=(LEXICAL_RETRIEVER,),
                corroborated=frozenset({VISIBLE.id}),
                latency_ms=4,
            )
        )
        return await super().passages(question, entitlement=entitlement, now=now)


class Kept(StoredRetrievals):
    """The store's shape over a list: ids are positions in it, as a string."""

    def __init__(self) -> None:
        self.events: list[RetrievalEvent] = []

    async def record(self, event: RetrievalEvent) -> str:
        self.events.append(event)
        return f"00000000-0000-4000-8000-{len(self.events):012d}"

    async def use(self, event_id: str, position: int) -> bool:
        index = int(event_id.rsplit("-", 1)[1]) - 1
        if not 0 <= index < len(self.events) or not 1 <= position <= self.events[index].returned:
            return False
        was = self.events[index]
        used = tuple(sorted({*was.used, position}))
        self.events[index] = RetrievalEvent(
            retrievers=was.retrievers,
            returned=was.returned,
            corroborated=was.corroborated,
            used=used,
            latency_ms=was.latency_ms,
        )
        return True

    async def recent(self, limit: int = 1_000) -> tuple[RetrievalEvent, ...]:
        return tuple(reversed(self.events))[:limit]


@pytest.fixture
def kept(client: TestClient) -> Iterator[Kept]:
    store = Kept()
    librarian = Grant(capability=Capability(value="admin:knowledge"), scope=Scope())
    state: Any = client.app.state  # type: ignore[attr-defined]
    state.retrievals = store
    state.passage_search = Noting(VISIBLE)
    state.gate = gate_wiring({**READER_GRANTS, LIBRARIAN: (librarian,)})
    yield store


def _asked(client: TestClient) -> Any:
    return client.post(f"{API_PREFIX}/answer", headers=headers(READER), json={"question": QUESTION})


def test_an_answer_names_the_retrieval_it_was_drawn_from_and_keeps_nothing_else(
    client: TestClient, kept: Kept
) -> None:
    """The model step's search is kept as one record, the passage shown and the one two
    retrievers agreed on, and the answer's `x-retrieval-id` names it. Delete this and the page has
    no id to send a followed citation's place back against, so nothing is ever used."""
    answered = _asked(client)

    assert answered.status_code == 200
    assert kept.events == [
        RetrievalEvent(retrievers=(LEXICAL_RETRIEVER,), returned=1, corroborated=1, latency_ms=4)
    ]
    assert answered.headers[RETRIEVAL_HEADER] == "00000000-0000-4000-8000-000000000001"


class Unkept(Kept):
    """A store that cannot keep anything, as a database gone away mid-answer would be."""

    async def record(self, event: RetrievalEvent) -> str:
        raise RuntimeError("the retrieval log could not be written")


def test_a_retrieval_that_cannot_be_kept_costs_the_answer_nothing(
    client: TestClient, kept: Kept
) -> None:
    """The store refusing the write, beside the positive case above: the person is still
    answered, and the header names no retrieval because none was kept. Delete this and the
    learning signal, which is evidence about the ranking, can fail a person's answer."""
    state: Any = client.app.state  # type: ignore[attr-defined]
    state.retrievals = Unkept()

    answered = _asked(client)

    assert answered.status_code == 200
    assert answered.headers[RETRIEVAL_HEADER] == ""
    assert "event: answer" in answered.text or "event: citation" in answered.text


def test_a_question_no_search_ran_for_names_no_retrieval(client: TestClient, kept: Kept) -> None:
    """A question the fast path answers runs no passage search, so nothing is kept and the header
    is empty: the positive case's sibling. Delete this and a rule's answer can be logged as a
    retrieval nobody could follow."""
    answered = client.post(
        f"{API_PREFIX}/answer",
        headers=headers(READER),
        json={"question": "what is the price of WEB-1001"},
    )

    assert answered.status_code == 200
    assert kept.events == []
    assert answered.headers[RETRIEVAL_HEADER] == ""


def test_a_followed_citation_is_kept_once_and_anything_else_is_one_404(
    client: TestClient, kept: Kept
) -> None:
    """The place of the passage followed is kept, a second follow keeps nothing more, and a place
    outside the list, one no list reaches and an id naming nothing answer alike. Delete this and a
    stranger can tell which retrieval ids exist, or one person's clicks count twice."""
    event_id = _asked(client).headers[RETRIEVAL_HEADER]
    path = f"{API_PREFIX}/retrievals/{event_id}/uses"

    for _ in range(2):
        assert client.post(path, headers=headers(READER), json={"position": 1}).status_code == 200
    assert kept.events[0].used == (1,)
    outside = client.post(path, headers=headers(READER), json={"position": 2})
    nothing = client.post(
        f"{API_PREFIX}/retrievals/00000000-0000-4000-8000-000000000009/uses",
        headers=headers(READER),
        json={"position": 1},
    )
    assert outside.status_code == nothing.status_code == 404
    assert outside.json()["message"] == nothing.json()["message"]
    past_any_list = client.post(path, headers=headers(READER), json={"position": 99})
    assert past_any_list.status_code == 422


def test_the_signal_is_read_by_a_knowledge_administrator_alone(
    client: TestClient, kept: Kept
) -> None:
    """Below the floor the administrator is told there is not enough yet, above it they get the
    rates; a reader who runs no part of the library gets the one 404. Delete this and the signal
    can be read by everybody, or answered with a number one afternoon decided."""
    path = f"{API_PREFIX}/retrievals/signal"

    assert client.get(path, headers=headers(READER)).status_code == 404
    few = client.get(path, headers=headers(LIBRARIAN)).json()
    assert few == {
        "enough": False,
        "told": NOT_ENOUGH_YET,
        "events": 0,
        "used_share": 0.0,
        "top_position_share": 0.0,
        "mean_first_used_position": 0.0,
        "latency_p95_ms": 0.0,
    }
    for _ in range(MINIMUM_EVENTS_FOR_A_SIGNAL):
        _asked(client)
    event_id = client.post(
        f"{API_PREFIX}/answer", headers=headers(READER), json={"question": QUESTION}
    ).headers[RETRIEVAL_HEADER]
    client.post(
        f"{API_PREFIX}/retrievals/{event_id}/uses", headers=headers(READER), json={"position": 1}
    )
    read = client.get(path, headers=headers(LIBRARIAN)).json()
    assert read["enough"] is True
    assert read["events"] == MINIMUM_EVENTS_FOR_A_SIGNAL + 1
    assert read["used_share"] == pytest.approx(1 / (MINIMUM_EVENTS_FOR_A_SIGNAL + 1))
    assert read["top_position_share"] == 1.0
