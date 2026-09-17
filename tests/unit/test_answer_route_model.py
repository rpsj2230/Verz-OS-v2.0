"""The answer route hands a question no rule answers to the model step this process was built with.

`tests/unit/test_model_lane.py` holds the step to what a model is shown. This is the wiring around
it: the real application from `create_app`, the real token path and registry, a real
`brain.models.calls.ModelCalls` behind `app.state.models`, and a passage search behind
`app.state.passage_search`, which is where `brain.app.lifespan` puts the registered document
tool. The frames are read off the HTTP response.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import model_lane_of, passage_search_for
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.gate.model_lane import DocumentSearchTool, ModelLane
from brain.knowledge.document_tools import SEARCH_DOCUMENTS
from brain.ops.model_service import ModelService
from brain.tools.startup import build_registry
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_answer_route import HOURS, OneRow
from tests.unit.test_api_routes import GRANTS, SOURCE
from tests.unit.test_model_calls import Ladder, Scripted, executor, rung
from tests.unit.test_model_lane import REPLY, VISIBLE, Passages, completion
from tests.unit.test_streaming import decode

#: The route test's wide reader, holding the knowledge plane and every passage field as well.
READER = "u_wide"

READER_GRANTS = {
    READER: (
        *GRANTS[READER],
        *(
            Grant(capability=Capability(value=one), scope=Scope())
            for one in (
                "read:knowledge",
                "read:knowledge.document",
                "read:knowledge.title",
                "read:knowledge.section",
                "read:knowledge.updated_at",
            )
        ),
    )
}


@pytest.fixture
def transport() -> Scripted:
    return Scripted(completion())


@pytest.fixture
def client(transport: Scripted) -> Iterator[TestClient]:
    """The real application with a model service and a passage search in place, and no database,
    so what the lifespan would have built from one is exactly what this puts there."""
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})
    owned = httpx.Client()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(READER_GRANTS)
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (HOURS,)
        app.state.models = ModelService(calls=calls, client=owned)
        app.state.passage_search = Passages(VISIBLE)
        yield c
    owned.close()


def test_the_route_answers_a_question_no_rule_answers_through_the_model_step(
    client: TestClient, transport: Scripted
) -> None:
    """**The route reaches a model.** A question no fast-path rule matches comes back as an event
    stream whose citation is the passage the reader may read, before prose that is the model's
    reply, and the provider was sent one request.

    Delete this and the route can go on building the lane with no model step, which every lane
    test passes, and no question asked of a real install ever reaches a model."""
    answered = client.post(
        f"{API_PREFIX}/answer",
        headers=headers(READER),
        json={"question": "how much annual leave do we get"},
    )

    assert answered.status_code == 200
    seen = [(one.event, one.data) for one in decode(answered.text)]
    names = [name for name, _ in seen]
    assert names.index("citation") < names.index("text")
    assert any(VISIBLE.id in data for name, data in seen if name == "citation")
    assert any(data.startswith(REPLY) for name, data in seen if name == "text")
    assert len(transport.sent) == 1


def test_a_question_a_rule_answers_reaches_no_model_through_the_route(
    client: TestClient, transport: Scripted
) -> None:
    """With a model step wired, a question the fast path answers is answered without one.

    Delete this and the route can hand every question to the model step first."""
    answered = client.post(
        f"{API_PREFIX}/answer",
        headers=headers(READER),
        json={"question": "what is the price of WEB-1001"},
    )

    assert answered.status_code == 200
    assert transport.sent == []


def test_a_process_missing_either_half_hands_the_lane_no_model_step() -> None:
    """A model service with no passage search, or a passage search with no model service, is no
    model step at all; both is one, holding exactly those two.

    Delete this and a process with a model and no database hands the lane a step that searches
    nothing, or one with passages and no executor calls a model it does not hold."""
    calls, _ = executor(Ladder(()), {})
    owned = httpx.Client()
    try:
        models = ModelService(calls=calls, client=owned)
        search = Passages()

        assert model_lane_of(SimpleNamespace(models=models, passage_search=None)) is None
        assert model_lane_of(SimpleNamespace(models=None, passage_search=search)) is None
        assert model_lane_of(SimpleNamespace()) is None
        assert model_lane_of(SimpleNamespace(models=models, passage_search=search)) == ModelLane(
            search=search, model=calls
        )
    finally:
        owned.close()


def test_the_passage_search_is_the_registered_document_tool_and_only_where_rows_are() -> None:
    """The search handed to the lane is the handler the registry holds for
    `knowledge.search_documents`, and a registry built with no row source has none to hand.

    Delete this and the lane can be handed a search of its own, which is a second decision about
    what a reader may retrieve beside the one the tool makes."""
    with_rows = build_registry(source=SOURCE, records=OneRow())
    found = passage_search_for(with_rows)

    assert isinstance(found, DocumentSearchTool)
    assert found.handler is with_rows.get(SEARCH_DOCUMENTS).handler
    assert passage_search_for(build_registry(source=SOURCE)) is None


def test_the_lifespan_without_a_database_builds_no_passage_search_and_no_ladder_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process with no database has nothing to search and nowhere to write a ladder, so the
    lifespan leaves both empty and the route hands the lane no model step. Pinned to no database
    in the test, with the environment carrying one as CI's does, per `tests.fixtures.no_database`.

    Delete this and a lite process with no database can be handed a writer or a search over a
    session factory that does not exist, which fails on the first question rather than at start."""
    as_if_ci_had_a_database(monkeypatch)
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app):
        assert app.state.passage_search is None
        assert app.state.default_ladder is None
        assert model_lane_of(app.state) is None
